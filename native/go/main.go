// Trusted stdin-only AST helper. It never loads or executes target imports.
package main

import (
	"bytes"
	"encoding/json"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

const toolID = "devsift-go"
const toolVersion = "1.0.0"
const engineVersion = "go1.21.3"

type region struct {
	StartLine   int `json:"start_line"`
	StartColumn int `json:"start_column"`
	EndLine     int `json:"end_line"`
	EndColumn   int `json:"end_column"`
}
type diagnostic struct {
	RuleID string `json:"rule_id"`
	Region region `json:"region"`
}

var fileTransport bool
var diagnosticsFile string

func report(complete bool, diagnostics []diagnostic, reason string) {
	if diagnostics == nil {
		diagnostics = []diagnostic{}
	}
	if fileTransport && diagnosticsFile != "" {
		output, err := os.OpenFile(diagnosticsFile, os.O_WRONLY|os.O_TRUNC, 0600)
		if err != nil {
			os.Exit(3)
		}
		encoder := json.NewEncoder(output)
		for _, item := range diagnostics {
			if encoder.Encode(item) != nil {
				output.Close()
				os.Exit(3)
			}
		}
		if output.Close() != nil {
			os.Exit(3)
		}
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{
			"protocol_version": "1", "tool_id": toolID, "tool_version": toolVersion,
			"complete": complete, "diagnostic_count": len(diagnostics), "reason": reason, "metadata": map[string]any{},
		})
		return
	}
	_ = json.NewEncoder(os.Stdout).Encode(map[string]any{
		"protocol_version": "1", "tool_id": toolID, "tool_version": toolVersion,
		"complete": complete, "diagnostics": diagnostics, "reason": reason, "metadata": map[string]any{},
	})
}

func request(body []byte) (string, string, bool) {
	if !utf8.Valid(body) {
		return "", "", false
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	opening, err := decoder.Token()
	if err != nil || opening != json.Delim('{') {
		return "", "", false
	}
	fields := map[string]json.RawMessage{}
	allowed := map[string]bool{"protocol_version": true, "path": true, "language": true, "source": true, "dialect": true}
	if fileTransport {
		delete(allowed, "source")
		allowed["source_file"] = true
		allowed["diagnostics_file"] = true
	}
	for decoder.More() {
		key, err := decoder.Token()
		name, valid := key.(string)
		if err != nil || !valid || !allowed[name] {
			return "", "", false
		}
		if _, duplicate := fields[name]; duplicate {
			return "", "", false
		}
		var value json.RawMessage
		if decoder.Decode(&value) != nil {
			return "", "", false
		}
		fields[name] = value
	}
	if closing, err := decoder.Token(); err != nil || closing != json.Delim('}') || len(fields) != len(allowed) {
		return "", "", false
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return "", "", false
	}
	if fileTransport {
		for _, key := range []string{"source_file", "diagnostics_file"} {
			var value string
			if json.Unmarshal(fields[key], &value) != nil || !filepath.IsAbs(value) {
				return "", "", false
			}
			info, err := os.Lstat(value)
			if err != nil || !info.Mode().IsRegular() {
				return "", "", false
			}
			if key == "source_file" {
				content, err := os.ReadFile(value)
				if err != nil || !utf8.Valid(content) {
					return "", "", false
				}
				fields["source"], err = json.Marshal(string(content))
				if err != nil {
					return "", "", false
				}
			} else {
				diagnosticsFile = value
			}
		}
	}
	var protocol, language, source, filename string
	if json.Unmarshal(fields["protocol_version"], &protocol) != nil || protocol != "1" ||
		json.Unmarshal(fields["language"], &language) != nil || language != "go" ||
		json.Unmarshal(fields["path"], &filename) != nil || filename == "" ||
		json.Unmarshal(fields["source"], &source) != nil || strings.ContainsRune(source, 0) ||
		!bytes.Equal(bytes.TrimSpace(fields["dialect"]), []byte("null")) {
		return "", "", false
	}
	return filename, source, true
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "--probe" {
		_ = json.NewEncoder(os.Stdout).Encode(map[string]any{
			"protocol_version": "1", "tool_id": toolID, "tool_version": toolVersion,
			"languages": []string{"go"}, "engine_versions": map[string]string{"go": runtime.Version()}, "transports": []string{"inline", "files"},
		})
		return
	}
	fileTransport = len(os.Args) == 2 && os.Args[1] == "--analyze-files"
	if !fileTransport && (len(os.Args) != 2 || os.Args[1] != "--analyze") {
		os.Exit(3)
	}
	defer func() {
		if recover() != nil {
			report(false, nil, "ANALYSIS_FAILED")
		}
	}()
	if runtime.Version() != engineVersion {
		report(false, nil, "ANALYSIS_FAILED")
		return
	}
	body, err := io.ReadAll(io.LimitReader(os.Stdin, 1_000_001))
	if err != nil || len(body) > 1_000_000 {
		report(false, nil, "UNSUPPORTED_SOURCE")
		return
	}
	filename, source, valid := request(body)
	if !valid {
		report(false, nil, "UNSUPPORTED_SOURCE")
		return
	}
	files := token.NewFileSet()
	file, err := parser.ParseFile(files, filename, source, parser.AllErrors|parser.ParseComments)
	if err != nil {
		report(false, nil, "PARSE_ERROR")
		return
	}
	imports := map[string]string{}
	ambiguous := map[string]bool{}
	for _, item := range file.Imports {
		value, err := strconv.Unquote(item.Path.Value)
		if err != nil {
			report(false, nil, "PARSE_ERROR")
			return
		}
		name := path.Base(value)
		if item.Name != nil {
			name = item.Name.Name
		}
		if name == "_" || name == "." {
			continue
		}
		if _, duplicate := imports[name]; duplicate {
			ambiguous[name] = true
		}
		imports[name] = value
	}
	for name := range ambiguous {
		delete(imports, name)
	}
	packageCall := func(expression ast.Expr, packagePath string, names ...string) bool {
		selector, ok := expression.(*ast.SelectorExpr)
		if !ok {
			return false
		}
		alias, ok := selector.X.(*ast.Ident)
		if !ok || alias.Obj != nil || imports[alias.Name] != packagePath {
			return false
		}
		for _, name := range names {
			if selector.Sel.Name == name {
				return true
			}
		}
		return false
	}
	groundedError := func(identifier *ast.Ident) bool {
		if identifier.Obj == nil {
			return false
		}
		switch declaration := identifier.Obj.Decl.(type) {
		case *ast.Field:
			typeName, ok := declaration.Type.(*ast.Ident)
			return ok && typeName.Name == "error" && typeName.Obj == nil
		case *ast.AssignStmt:
			if len(declaration.Lhs) != 1 || len(declaration.Rhs) != 1 {
				return false
			}
			call, ok := declaration.Rhs[0].(*ast.CallExpr)
			return ok && (packageCall(call.Fun, "errors", "New") || packageCall(call.Fun, "fmt", "Errorf"))
		case *ast.ValueSpec:
			if declaration.Type != nil {
				typeName, ok := declaration.Type.(*ast.Ident)
				return ok && typeName.Name == "error" && typeName.Obj == nil
			}
			if len(declaration.Names) != 1 || len(declaration.Values) != 1 {
				return false
			}
			call, ok := declaration.Values[0].(*ast.CallExpr)
			return ok && (packageCall(call.Fun, "errors", "New") || packageCall(call.Fun, "fmt", "Errorf"))
		}
		return false
	}
	lineStarts := []int{0}
	for index := range source {
		if source[index] == '\n' {
			lineStarts = append(lineStarts, index+1)
		}
	}
	coordinateAt := func(offset int) (int, int) {
		line := sort.Search(len(lineStarts), func(index int) bool { return lineStarts[index] > offset }) - 1
		return line + 1, utf8.RuneCountInString(source[lineStarts[line]:offset]) + 1
	}
	var findings []diagnostic
	add := func(rule string, node ast.Node) {
		if !fileTransport && len(findings) >= 1000 {
			panic("limit")
		}
		start, end := files.File(node.Pos()).Offset(node.Pos()), files.File(node.End()).Offset(node.End())
		line, column := coordinateAt(start)
		endLine, endColumn := coordinateAt(end)
		findings = append(findings, diagnostic{rule, region{line, column, endLine, endColumn}})
	}
	ast.Inspect(file, func(node ast.Node) bool {
		if call, ok := node.(*ast.CallExpr); ok {
			if packageCall(call.Fun, "fmt", "Print", "Println") {
				add("LOG001", call)
			}
			if !excludedPath(filename) && packageCall(call.Fun, "net/http", "Get", "Post") && len(call.Args) > 0 {
				if literal, ok := call.Args[0].(*ast.BasicLit); ok && literal.Kind == token.STRING {
					value, err := strconv.Unquote(literal.Value)
					endpoint, parseError := url.Parse(value)
					if err == nil && parseError == nil && endpoint.Host != "" && (endpoint.Scheme == "http" || endpoint.Scheme == "https") {
						add("HC001", literal)
					}
				}
			}
		}
		if branch, ok := node.(*ast.IfStmt); ok && len(branch.Body.List) == 0 {
			if comparison, ok := branch.Cond.(*ast.BinaryExpr); ok && comparison.Op == token.NEQ {
				left, leftOK := comparison.X.(*ast.Ident)
				right, rightOK := comparison.Y.(*ast.Ident)
				if leftOK && rightOK && ((left.Name == "nil" && left.Obj == nil && groundedError(right)) ||
					(right.Name == "nil" && right.Obj == nil && groundedError(left))) {
					add("LOG002", branch)
				}
			}
		}
		return true
	})
	sort.Slice(findings, func(i, j int) bool {
		a, b := findings[i], findings[j]
		if a.Region.StartLine != b.Region.StartLine {
			return a.Region.StartLine < b.Region.StartLine
		}
		if a.Region.StartColumn != b.Region.StartColumn {
			return a.Region.StartColumn < b.Region.StartColumn
		}
		return a.RuleID < b.RuleID
	})
	report(true, findings, "COMPLETED")
}

func excludedPath(filename string) bool {
	normalized := strings.ToLower(strings.ReplaceAll(filename, "\\", "/"))
	if strings.HasSuffix(normalized, "_test.go") {
		return true
	}
	for _, part := range strings.Split(normalized, "/") {
		switch part {
		case "test", "tests", "testdata", "fixtures", "config", "configuration":
			return true
		}
	}
	return false
}
