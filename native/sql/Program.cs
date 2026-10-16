using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Microsoft.SqlServer.TransactSql.ScriptDom;

namespace DevSift.Sql;

public static class Program
{
    public const string ToolVersion = "1.0.0";
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
                    languages = new[] { "sql" }, engine_versions = new { scriptdom = ScriptDomVersion } });
                return 0;
            }
            if (args.Length != 1 || args[0] != "--analyze")
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
            string[] fields = ["protocol_version", "path", "language", "source", "dialect"];
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
            var source = Required("source");
            if (source.Length > 2_000_000 || source.Contains('\0'))
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
            Write(new { protocol_version = "1", tool_id = "devsift-sql", tool_version = ToolVersion,
                complete = true, diagnostics = Array.Empty<object>(), reason = "COMPLETED",
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

    static void Write(object value) => Console.WriteLine(JsonSerializer.Serialize(value));
    static void Failure(string reason) => Write(new { protocol_version = "1", tool_id = "devsift-sql",
        tool_version = ToolVersion, complete = false, diagnostics = Array.Empty<object>(), reason, metadata = new { } });
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
    public static object Region(string source, int start, int length)
    {
        if (start < 0 || length < 0 || start > source.Length - length)
            throw new ArgumentOutOfRangeException();
        (int Line, int Column) Position(int offset)
        {
            if (offset > 0 && offset < source.Length && char.IsHighSurrogate(source[offset - 1]) && char.IsLowSurrogate(source[offset]))
                throw new ArgumentOutOfRangeException();
            int line = 1, column = 1;
            for (int i = 0; i < offset; i++)
            {
                if (source[i] == '\n') { line++; column = 1; }
                else if (!char.IsLowSurrogate(source[i])) column++;
            }
            return (line, column);
        }
        var first = Position(start);
        var last = Position(start + length);
        return new { start_line = first.Line, start_column = first.Column, end_line = last.Line, end_column = last.Column };
    }
}
