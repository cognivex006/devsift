using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;

internal static class Program
{
    const string ToolId = "devsift-roslyn";
    const string ToolVersion = "1.0.0";
    const string ExpectedEngine = "4.13.0.0";
    static readonly HashSet<string> EndpointMethods = new(StringComparer.Ordinal)
    {
        "GetAsync", "GetStringAsync", "GetByteArrayAsync", "GetStreamAsync",
        "PostAsync", "PutAsync", "PatchAsync", "DeleteAsync"
    };
    record Position(int start_line, int start_column, int end_line, int end_column);
    record Finding(string rule_id, Position region);

    static int Main(string[] arguments)
    {
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
        string engine = typeof(CSharpSyntaxTree).Assembly.GetName().Version?.ToString() ?? "unknown";
        if (arguments.SequenceEqual(new[] { "--probe" }))
        {
            Console.WriteLine(JsonSerializer.Serialize(new
            {
                protocol_version = "1", tool_id = ToolId, tool_version = ToolVersion,
                languages = new[] { "csharp" }, engine_versions = new { roslyn = engine }
            }));
            return 0;
        }
        if (!arguments.SequenceEqual(new[] { "--analyze" })) return 3;
        try
        {
            if (engine != ExpectedEngine) return Report(false, [], "ANALYSIS_FAILED");
            var input = new StringBuilder();
            var buffer = new char[8192];
            int count;
            while ((count = Console.In.Read(buffer)) > 0)
            {
                if (input.Length + count > 1_000_000) return Report(false, [], "UNSUPPORTED_SOURCE");
                input.Append(buffer, 0, count);
            }
            using JsonDocument document = JsonDocument.Parse(input.ToString(), new JsonDocumentOptions { MaxDepth = 16 });
            JsonElement request = document.RootElement;
            if (request.ValueKind != JsonValueKind.Object) return Report(false, [], "UNSUPPORTED_SOURCE");
            var properties = request.EnumerateObject().ToArray();
            string[] required = ["protocol_version", "path", "language", "source", "dialect"];
            if (properties.Length != required.Length || properties.Select(p => p.Name).Distinct().Count() != required.Length
                || properties.Any(p => !required.Contains(p.Name))) return Report(false, [], "UNSUPPORTED_SOURCE");
            if (request.GetProperty("protocol_version").GetString() != "1"
                || request.GetProperty("language").GetString() != "csharp"
                || request.GetProperty("dialect").ValueKind != JsonValueKind.Null)
                return Report(false, [], "UNSUPPORTED_SOURCE");
            string path = request.GetProperty("path").GetString() ?? "";
            string source = request.GetProperty("source").GetString() ?? throw new JsonException();
            if (path.Length == 0 || source.Contains('\0')) return Report(false, [], "UNSUPPORTED_SOURCE");
            var tree = CSharpSyntaxTree.ParseText(source, new CSharpParseOptions(LanguageVersion.CSharp13));
            if (tree.GetDiagnostics().Any(d => d.Severity == DiagnosticSeverity.Error))
                return Report(false, [], "PARSE_ERROR");
            // Only this helper's trusted runtime libraries participate; no target
            // projects, build props, analyzers, generators or references are read.
            string[] trusted = ((string?)AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") ?? "").Split(Path.PathSeparator);
            var references = trusted.Where(File.Exists).Select(path => MetadataReference.CreateFromFile(path));
            var compilation = CSharpCompilation.Create("DevSift.Snapshot", [tree], references,
                new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));
            var model = compilation.GetSemanticModel(tree);
            var findings = new List<Finding>();
            void Add(string rule, TextSpan span)
            {
                if (findings.Count >= 1000) throw new InvalidOperationException();
                var start = Coordinate(source, span.Start);
                var end = Coordinate(source, span.End);
                findings.Add(new Finding(rule, new Position(start.line, start.column, end.line, end.column)));
            }
            bool endpointExcluded = ExcludedPath(path);
            foreach (SyntaxNode node in tree.GetRoot().DescendantNodes())
            {
                if (node is CatchClauseSyntax caught && caught.Block.Statements.Count == 0)
                {
                    ITypeSymbol? exception = caught.Declaration is null ? null : model.GetTypeInfo(caught.Declaration.Type).Type;
                    bool cancellation = false;
                    for (var type = exception as INamedTypeSymbol; type is not null; type = type.BaseType)
                        cancellation |= FrameworkType(type, typeof(OperationCanceledException));
                    if (!cancellation) Add("LOG002", caught.Span);
                }
                if (node is InvocationExpressionSyntax invocation
                    && model.GetSymbolInfo(invocation).Symbol is IMethodSymbol method)
                {
                    if (FrameworkType(method.ContainingType, typeof(Console)) && method.Name is "Write" or "WriteLine")
                        Add("LOG001", invocation.Span);
                    if (!endpointExcluded && !ExcludedContext(invocation)
                        && FrameworkType(method.ContainingType, typeof(System.Net.Http.HttpClient)) && EndpointMethods.Contains(method.Name)
                        && invocation.ArgumentList.Arguments.Count > 0)
                        CheckLiteral(invocation.ArgumentList.Arguments[0].Expression, Add);
                }
                if (!endpointExcluded && node is ObjectCreationExpressionSyntax creation
                    && !ExcludedContext(creation)
                    && model.GetSymbolInfo(creation).Symbol is IMethodSymbol constructor
                    && FrameworkType(constructor.ContainingType, typeof(System.Net.Http.HttpRequestMessage))
                    && creation.ArgumentList?.Arguments.Count > 1)
                    CheckLiteral(creation.ArgumentList.Arguments[1].Expression, Add);
            }
            return Report(true, findings.OrderBy(f => f.region.start_line).ThenBy(f => f.region.start_column)
                .ThenBy(f => f.rule_id, StringComparer.Ordinal).ToArray(), "COMPLETED");
        }
        catch { return Report(false, [], "ANALYSIS_FAILED"); }
    }

    static void CheckLiteral(ExpressionSyntax expression, Action<string, TextSpan> add)
    {
        if (expression is LiteralExpressionSyntax literal && literal.IsKind(SyntaxKind.StringLiteralExpression)
            && Uri.TryCreate(literal.Token.ValueText, UriKind.Absolute, out Uri? uri)
            && uri.Scheme is "http" or "https") add("HC001", literal.Span);
    }

    static bool FrameworkType(INamedTypeSymbol symbol, Type runtimeType) =>
        symbol.ToDisplayString() == runtimeType.FullName
        && symbol.Locations.All(location => location.IsInMetadata)
        && symbol.ContainingAssembly.Identity.Name == runtimeType.Assembly.GetName().Name;

    static bool ExcludedPath(string path)
    {
        string normalized = path.Replace('\\', '/').ToLowerInvariant();
        return normalized.Split('/').Any(p => p is "test" or "tests" or "testdata" or "fixtures"
                   or "config" or "configuration" or "options")
            || normalized.EndsWith("tests.cs") || normalized.EndsWith(".test.cs");
    }

    static bool ExcludedContext(SyntaxNode node) => node.Ancestors().Any(parent =>
        parent is TypeDeclarationSyntax type && new[] { "Options", "Settings", "Configuration" }
            .Any(suffix => type.Identifier.ValueText.EndsWith(suffix, StringComparison.Ordinal))
        || parent is MethodDeclarationSyntax method && method.AttributeLists.SelectMany(a => a.Attributes)
            .Any(a => a.Name.ToString().Split('.').Last() is "Fact" or "Theory" or "Test" or "TestMethod"));

    static (int line, int column) Coordinate(string source, int offset)
    {
        int line = 1, column = 1;
        for (int index = 0; index < offset; index++)
        {
            char value = source[index];
            if (value == '\n') { line++; column = 1; }
            else if (char.IsHighSurrogate(value) && index + 1 < offset && char.IsLowSurrogate(source[index + 1]))
            { index++; column++; }
            else column++;
        }
        return (line, column);
    }

    static int Report(bool complete, IEnumerable<Finding> diagnostics, string reason)
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            protocol_version = "1", tool_id = ToolId, tool_version = ToolVersion,
            complete, diagnostics, reason, metadata = new { }
        }));
        return 0;
    }
}
