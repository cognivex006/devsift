using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Microsoft.SqlServer.TransactSql.ScriptDom;

namespace DevSift.Sql;

public static class Program
{
    static bool FileTransport;
    static string? DiagnosticsFile;
    static string SnapshotPath(JsonElement request, string key)
    {
        string value = request.GetProperty(key).GetString() ?? throw new JsonException();
        if (!Path.IsPathFullyQualified(value) || !File.Exists(value)
            || (File.GetAttributes(value) & (FileAttributes.ReparsePoint | FileAttributes.Directory)) != 0)
            throw new JsonException();
        return value;
    }
    public const string ToolVersion = "1.1.0";
    public const string ScriptDomVersion = "161.8901.0";

    public static int Main(string[] args)
    {
        Console.InputEncoding = new UTF8Encoding(false, true);
        Console.OutputEncoding = new UTF8Encoding(false);
        try
        {
            var assembly = typeof(TSqlParser).Assembly;
            if (assembly.GetName().Version != new Version(16, 1, 0, 0)
                || FileVersionInfo.GetVersionInfo(assembly.Location).FileVersion != "16.1.8901.0")
                throw new InvalidOperationException();
            if (args.Length == 1 && args[0] == "--probe")
            {
                Write(new { protocol_version = "1", tool_id = "devsift-sql", tool_version = ToolVersion,
                    languages = new[] { "sql" }, engine_versions = new { scriptdom = ScriptDomVersion }, transports = new[] { "inline", "files" } });
                return 0;
            }
            FileTransport = args.Length == 1 && args[0] == "--analyze-files";
            if (!FileTransport && (args.Length != 1 || args[0] != "--analyze"))
            {
                Failure("ANALYSIS_FAILED");
                return 0;
            }
            var buffer = new char[2_000_001];
            int length = 0;
            while (length < buffer.Length)
            {
                int read = Console.In.Read(buffer, length, buffer.Length - length);
                if (read == 0) break;
                length += read;
            }
            if (length > 2_000_000) throw new InvalidOperationException();
            using var document = JsonDocument.Parse(new string(buffer, 0, length), new JsonDocumentOptions { MaxDepth = 16 });
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new InvalidOperationException();
            var values = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
            foreach (var property in root.EnumerateObject())
                if (!values.TryAdd(property.Name, property.Value)) throw new InvalidOperationException();
            string[] fields = FileTransport ? ["protocol_version", "path", "language", "source_file", "diagnostics_file", "dialect"]
                : ["protocol_version", "path", "language", "source", "dialect"];
            if (values.Count != fields.Length || fields.Any(field => !values.ContainsKey(field)))
                throw new InvalidOperationException();
            string Required(string field) => values[field].ValueKind == JsonValueKind.String
                ? values[field].GetString()! : throw new InvalidOperationException();
            if (Required("protocol_version") != "1" || Required("language") != "sql")
                throw new InvalidOperationException();
            var path = Required("path");
            if (path.Length is 0 or > 4096 || path.Any(c => c < 32 || "\\:<>\"|?*".Contains(c))
                || path.Split('/').Any(part => part is "" or "." or ".."))
                throw new InvalidOperationException();
            if (FileTransport) DiagnosticsFile = SnapshotPath(root, "diagnostics_file");
            var source = FileTransport ? new UTF8Encoding(false, true).GetString(File.ReadAllBytes(SnapshotPath(root, "source_file"))) : Required("source");
            if (!FileTransport && source.Length > 2_000_000 || source.Contains('\0'))
            {
                Failure("UNSUPPORTED_SOURCE");
                return 0;
            }
            var dialect = values["dialect"].ValueKind == JsonValueKind.String ? values["dialect"].GetString() : null;
            TSqlParser? parser = dialect switch
            {
                "tsql150" => new TSql150Parser(true),
                "tsql160" => new TSql160Parser(true),
                _ => null
            };
            if (parser is null)
            {
                Failure("UNSUPPORTED_DIALECT");
                return 0;
            }
            using var reader = new StringReader(source);
            var fragment = parser.Parse(reader, out var errors);
            if (fragment is null || errors.Count != 0)
            {
                Failure("PARSE_ERROR");
                return 0;
            }
            var facts = new MetadataVisitor();
            fragment.Accept(facts);
            var rules = new DynamicSqlVisitor(parser, source, FileTransport);
            fragment.Accept(rules);
            Write(new { protocol_version = "1", tool_id = "devsift-sql", tool_version = ToolVersion,
                complete = rules.Complete, diagnostics = rules.Diagnostics,
                reason = rules.Complete ? "COMPLETED" : "ANALYSIS_FAILED",
                metadata = new { dialect, unqualified_references = facts.UnqualifiedReferences, ddl_statements = facts.DdlStatements } });
            return 0;
        }
        catch (Exception)
        {
            // Neither parser errors, input, identifiers nor exception messages
            // leave the helper. The host retains an incomplete outcome.
            Failure("ANALYSIS_FAILED");
            return 0;
        }
    }

    static void Write(object value)
    {
        if (FileTransport && DiagnosticsFile is not null)
        {
            var report = JsonSerializer.SerializeToElement(value);
            if (report.TryGetProperty("diagnostics", out var diagnostics))
            {
                long count = 0;
                using (var output = new StreamWriter(DiagnosticsFile, false, new UTF8Encoding(false)))
                    foreach (var item in diagnostics.EnumerateArray()) { output.WriteLine(item.GetRawText()); count++; }
                Console.WriteLine(JsonSerializer.Serialize(new { protocol_version = "1", tool_id = "devsift-sql",
                    tool_version = ToolVersion, complete = report.GetProperty("complete").GetBoolean(),
                    diagnostic_count = count, reason = report.GetProperty("reason").GetString(), metadata = report.GetProperty("metadata") }));
                return;
            }
        }
        Console.WriteLine(JsonSerializer.Serialize(value));
    }
    static void Failure(string reason) => Write(new { protocol_version = "1", tool_id = "devsift-sql",
        tool_version = ToolVersion, complete = false, diagnostics = Array.Empty<object>(), reason, metadata = new { } });
}

// This deliberately bounded flow domain tracks only local straight-line string
// assembly into AST execution sinks. It is not a whole-program taint engine.
public sealed class DynamicSqlVisitor(TSqlParser parser, string source, bool fileTransport = false) : TSqlFragmentVisitor
{
    enum Kind { Literal, Input, QuotedIdentifier, Unknown }
    sealed record Part(Kind Kind, string Text = "");
    Dictionary<string, Part[]> variables = new(StringComparer.OrdinalIgnoreCase);
    HashSet<string> unboundedUnicodeStorage = new(StringComparer.OrdinalIgnoreCase);
    static Part[] Unknown => [new(Kind.Unknown)];
    public bool Complete { get; private set; } = true;
    public List<object> Diagnostics { get; } = [];

    static Part[] Join(Part[] left, Part[] right)
    {
        if (left.Length + right.Length > 256) return Unknown;
        Part[] joined = [.. left, .. right];
        // Assignment to nvarchar(max) does not prevent truncation in an earlier
        // finite-width concatenation. Refuse identifier safety when even this
        // conservative UTF-16 worst-case bound exceeds nvarchar's finite width.
        if (joined.Any(part => part.Kind == Kind.QuotedIdentifier)
            && joined.All(part => part.Kind is Kind.Literal or Kind.QuotedIdentifier)
            && joined.Sum(part => part.Kind == Kind.QuotedIdentifier ? 258L : part.Text.Length) > 4000)
            return Unknown;
        return joined;
    }

    Part[] Value(ScalarExpression? expression, int depth = 0)
    {
        if (depth > 32) return Unknown;
        return expression switch
        {
            StringLiteral literal => [new(Kind.Literal, literal.Value)],
            IntegerLiteral literal => [new(Kind.Literal, literal.Value)],
            NullLiteral => [new(Kind.Literal)],
            VariableReference variable => variables.TryGetValue(variable.Name, out var known) ? known : [new(Kind.Input)],
            ParenthesisExpression parentheses => Value(parentheses.Expression, depth + 1),
            BinaryExpression binary when binary.BinaryExpressionType == BinaryExpressionType.Add =>
                Join(Value(binary.FirstExpression, depth + 1), Value(binary.SecondExpression, depth + 1)),
            FunctionCall function when function.CallTarget is null
                && function.FunctionName.Value.Equals("QUOTENAME", StringComparison.OrdinalIgnoreCase)
                && (function.Parameters.Count == 1 || function.Parameters.Count == 2
                    && function.Parameters[1] is StringLiteral delimiter && delimiter.Value is "[" or "\"") =>
                [new(Kind.QuotedIdentifier)],
            _ => Unknown
        };
    }

    public override void ExplicitVisit(TSqlBatch node)
    {
        variables.Clear();
        unboundedUnicodeStorage.Clear();
        base.ExplicitVisit(node);
    }

    static bool PreservesQuotedIdentifier(DataTypeReference? dataType) =>
        dataType is SqlDataTypeReference sql && sql.SqlDataTypeOption == SqlDataTypeOption.NVarChar
        && sql.Parameters.Count == 1 && sql.Parameters[0] is MaxLiteral;

    Part[] Stored(string name, Part[] value) => value.Any(part => part.Kind == Kind.QuotedIdentifier)
        && !unboundedUnicodeStorage.Contains(name) ? Unknown : value;

    public override void ExplicitVisit(DeclareVariableStatement node)
    {
        foreach (var declaration in node.Declarations)
        {
            string name = declaration.VariableName.Value;
            if (PreservesQuotedIdentifier(declaration.DataType)) unboundedUnicodeStorage.Add(name);
            else unboundedUnicodeStorage.Remove(name);
            variables[name] = Stored(name, Value(declaration.Value));
        }
    }

    public override void ExplicitVisit(SetVariableStatement node)
    {
        var value = Value(node.Expression);
        if (node.AssignmentKind == AssignmentKind.AddEquals)
            value = Join(Value(node.Variable), value);
        else if (node.AssignmentKind != AssignmentKind.Equals)
            value = Unknown;
        variables[node.Variable.Name] = Stored(node.Variable.Name, value);
    }

    public override void ExplicitVisit(SelectSetVariable node)
    {
        variables[node.Variable.Name] = Unknown;
        Complete = false;
    }

    public override void ExplicitVisit(AssignmentSetClause node)
    {
        if (node.Variable is not null) { variables[node.Variable.Name] = Unknown; Complete = false; }
    }

    public override void ExplicitVisit(FetchCursorStatement node) { Complete = false; Invalidate(); }
    public override void ExplicitVisit(GoToStatement node) { Complete = false; Invalidate(); }
    public override void ExplicitVisit(ReturnStatement node) { Complete = false; Invalidate(); }
    public override void ExplicitVisit(ExecuteAsStatement node) { Complete = false; Invalidate(); }
    public override void ExplicitVisit(RevertStatement node) { Complete = false; Invalidate(); }

    void Invalidate()
    {
        foreach (var name in variables.Keys.ToArray()) variables[name] = Unknown;
    }

    public override void ExplicitVisit(IfStatement node)
    {
        Complete = false;
        Invalidate();
        node.ThenStatement?.Accept(this);
        Invalidate();
        node.ElseStatement?.Accept(this);
        Invalidate();
    }

    public override void ExplicitVisit(WhileStatement node)
    {
        Complete = false;
        Invalidate();
        node.Statement?.Accept(this);
        Invalidate();
    }

    public override void ExplicitVisit(TryCatchStatement node)
    {
        Complete = false;
        Invalidate();
        node.TryStatements?.Accept(this);
        Invalidate();
        node.CatchStatements?.Accept(this);
        Invalidate();
    }

    public override void ExplicitVisit(CreateFunctionStatement node) => Complete = false;
    public override void ExplicitVisit(AlterFunctionStatement node) => Complete = false;
    public override void ExplicitVisit(CreateOrAlterFunctionStatement node) => Complete = false;
    public override void ExplicitVisit(CreateTriggerStatement node) => Complete = false;
    public override void ExplicitVisit(AlterTriggerStatement node) => Complete = false;
    public override void ExplicitVisit(CreateOrAlterTriggerStatement node) => Complete = false;

    void Procedure(ProcedureStatementBodyBase node)
    {
        var outer = variables;
        var outerStorage = unboundedUnicodeStorage;
        variables = new(StringComparer.OrdinalIgnoreCase);
        unboundedUnicodeStorage = new(StringComparer.OrdinalIgnoreCase);
        foreach (var parameter in node.Parameters)
        {
            variables[parameter.VariableName.Value] = [new(Kind.Input)];
            if (PreservesQuotedIdentifier(parameter.DataType)) unboundedUnicodeStorage.Add(parameter.VariableName.Value);
        }
        if (node.StatementList is null || node.MethodSpecifier is not null) Complete = false;
        node.StatementList?.Accept(this);
        variables = outer;
        unboundedUnicodeStorage = outerStorage;
    }
    public override void ExplicitVisit(CreateProcedureStatement node) => Procedure(node);
    public override void ExplicitVisit(AlterProcedureStatement node) => Procedure(node);
    public override void ExplicitVisit(CreateOrAlterProcedureStatement node) => Procedure(node);

    bool GroundedSql(IEnumerable<Part> parts)
    {
        foreach (var part in parts.Where(part => part.Kind == Kind.Literal))
        {
            using var reader = new StringReader(part.Text);
            var tokens = parser.GetTokenStream(reader, out _);
            if (tokens.Any(token => token.TokenType is TSqlTokenType.Select or TSqlTokenType.Insert
                or TSqlTokenType.Update or TSqlTokenType.Delete or TSqlTokenType.Execute
                or TSqlTokenType.Create or TSqlTokenType.Alter or TSqlTokenType.Drop or TSqlTokenType.Merge))
                return true;
        }
        return false;
    }

    bool OnlyTableIdentifiers(Part[] parts)
    {
        var text = new StringBuilder();
        var markers = new HashSet<string>(StringComparer.Ordinal);
        int count = 0;
        foreach (var part in parts)
        {
            if (part.Kind == Kind.Literal) text.Append(part.Text);
            else if (part.Kind == Kind.QuotedIdentifier)
            {
                string marker = "__devsift_identifier_" + count++ + "__";
                // Prevent preexisting literal content from impersonating markers.
                if (parts.Any(item => item.Kind == Kind.Literal && item.Text.Contains(marker))) return false;
                markers.Add(marker);
                text.Append(marker);
            }
            else return false;
        }
        using var reader = new StringReader(text.ToString());
        var fragment = parser.Parse(reader, out var errors);
        if (fragment is null || errors.Count != 0) return false;
        var visitor = new TableMarkerVisitor(markers);
        fragment.Accept(visitor);
        return visitor.Found.SetEquals(markers);
    }

    void Sink(ExecuteStatement node, Part[] value)
    {
        if (value.Any(part => part.Kind == Kind.Unknown)) { Complete = false; return; }
        if (value.All(part => part.Kind == Kind.Literal)) return;
        if (!GroundedSql(value)) { Complete = false; return; }
        if (value.Any(part => part.Kind == Kind.Input))
        {
            if (!fileTransport && Diagnostics.Count >= 1000) { Complete = false; return; }
            Diagnostics.Add(new { rule_id = "SEC003", region = SourceCoordinates.Region(source, node.StartOffset, node.FragmentLength) });
        }
        else if (!OnlyTableIdentifiers(value)) Complete = false;
    }

    public override void ExplicitVisit(ExecuteStatement node)
    {
        var specification = node.ExecuteSpecification;
        if (specification.LinkedServer is not null || specification.ExecuteContext is not null)
        { Complete = false; Invalidate(); return; }
        if (specification.ExecutableEntity is ExecutableStringList strings)
        {
            Part[] value = [];
            foreach (var expression in strings.Strings) value = Join(value, Value(expression));
            Sink(node, value);
        }
        else if (specification.ExecutableEntity is ExecutableProcedureReference procedure)
        {
            var name = procedure.ProcedureReference?.ProcedureReference?.Name;
            bool builtin = name is not null && name.BaseIdentifier.Value.Equals("sp_executesql", StringComparison.OrdinalIgnoreCase)
                && (name.Identifiers.Count == 1 || name.Identifiers.Count == 2
                    && name.SchemaIdentifier.Value.Equals("sys", StringComparison.OrdinalIgnoreCase));
            if (!builtin) { Complete = false; Invalidate(); return; }
            var arguments = procedure.Parameters;
            var namedStatements = arguments.Where(argument => argument.Variable?.Name.Equals("@stmt", StringComparison.OrdinalIgnoreCase) == true).ToArray();
            if (namedStatements.Length > 1 || namedStatements.Length == 1 && arguments.Any(argument => argument.Variable is null))
            { Complete = false; Invalidate(); return; }
            var statement = namedStatements.FirstOrDefault()
                ?? arguments.FirstOrDefault(argument => argument.Variable is null);
            if (statement is null) Complete = false;
            else Sink(node, Value(statement.ParameterValue));
            foreach (var argument in arguments.Where(argument => argument.IsOutput))
                if (argument.ParameterValue is VariableReference variable) variables[variable.Name] = Unknown;
        }
        else { Complete = false; Invalidate(); }
        if (specification.Variable is not null) variables[specification.Variable.Name] = Unknown;
    }

    sealed class TableMarkerVisitor(HashSet<string> expected) : TSqlFragmentVisitor
    {
        public HashSet<string> Found { get; } = new(StringComparer.Ordinal);
        public override void Visit(NamedTableReference node)
        {
            foreach (var identifier in node.SchemaObject.Identifiers)
                if (expected.Contains(identifier.Value)) Found.Add(identifier.Value);
        }
    }
}

public sealed class MetadataVisitor : TSqlFragmentVisitor
{
    public int UnqualifiedReferences { get; private set; }
    public int DdlStatements { get; private set; }
    public override void Visit(NamedTableReference node)
    {
        if (node.SchemaObject.Identifiers.Count == 1) UnqualifiedReferences++;
    }
    public override void Visit(CreateTableStatement node) => DdlStatements++;
    public override void Visit(DropTableStatement node) => DdlStatements++;
    public override void Visit(CreateViewStatement node) => DdlStatements++;
    public override void Visit(AlterViewStatement node) => DdlStatements++;
    public override void Visit(DropViewStatement node) => DdlStatements++;
    public override void Visit(CreateProcedureStatement node) => DdlStatements++;
    public override void Visit(AlterProcedureStatement node) => DdlStatements++;
    public override void Visit(DropProcedureStatement node) => DdlStatements++;
    public override void Visit(CreateFunctionStatement node) => DdlStatements++;
    public override void Visit(AlterFunctionStatement node) => DdlStatements++;
    public override void Visit(DropFunctionStatement node) => DdlStatements++;
    public override void Visit(CreateIndexStatement node) => DdlStatements++;
    public override void Visit(DropIndexStatement node) => DdlStatements++;
    public override void Visit(CreateSchemaStatement node) => DdlStatements++;
    public override void Visit(DropSchemaStatement node) => DdlStatements++;
}

public static class SourceCoordinates
{
    static readonly System.Runtime.CompilerServices.ConditionalWeakTable<string, int[]> Lines = new();
    public static object Region(string source, int start, int length)
    {
        if (start < 0 || length < 0 || start > source.Length - length)
            throw new ArgumentOutOfRangeException();
        (int Line, int Column) Position(int offset)
        {
            if (offset > 0 && offset < source.Length && char.IsHighSurrogate(source[offset - 1]) && char.IsLowSurrogate(source[offset]))
                throw new ArgumentOutOfRangeException();
            var starts = Lines.GetValue(source, text =>
            {
                var lines = new List<int> { 0 };
                for (int index = 0; index < text.Length; index++) if (text[index] == '\n') lines.Add(index + 1);
                return lines.ToArray();
            });
            int line = Array.BinarySearch(starts, offset);
            if (line < 0) line = ~line - 1;
            int column = 1;
            for (int i = starts[line]; i < offset; i++) if (!char.IsLowSurrogate(source[i])) column++;
            return (line + 1, column);
        }
        var first = Position(start);
        var last = Position(start + length);
        return new { start_line = first.Line, start_column = first.Column, end_line = last.Line, end_column = last.Column };
    }
}
