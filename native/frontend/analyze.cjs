'use strict';

const fs = require('node:fs');
const { Linter } = require('eslint');
const parser = require('@typescript-eslint/parser');
const ts = require('typescript');
const TOOL_ID = 'devsift-typescript';
const TOOL_VERSION = '1.1.0';
const versions = {
  eslint: require('eslint/package.json').version,
  parser: require('@typescript-eslint/parser/package.json').version,
  typescript: require('typescript/package.json').version,
};
const pinned = versions.eslint === '10.12.0' && versions.parser === '8.71.2' && versions.typescript === '6.0.3';
const probe = { protocol_version: '1', tool_id: TOOL_ID, tool_version: TOOL_VERSION,
  languages: ['typescript', 'javascript'], engine_versions: versions };

function output(complete, diagnostics = [], reason = 'ANALYSIS_FAILED') {
  process.stdout.write(JSON.stringify({ protocol_version: '1', tool_id: TOOL_ID,
    tool_version: TOOL_VERSION, complete, diagnostics, reason, metadata: {} }));
}

function position(source, offset) {
  const prefix = source.slice(0, offset);
  const line = prefix.split('\n').length;
  const start = prefix.lastIndexOf('\n') + 1;
  return [line, Array.from(source.slice(start, offset)).length + 1];
}

function region(source, node) {
  const [start_line, start_column] = position(source, node.range[0]);
  const [end_line, end_column] = position(source, node.range[1]);
  return { start_line, start_column, end_line, end_column };
}

function strictRequest(bytes) {
  const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  const value = JSON.parse(text); // Reject comments, trailing data and non-JSON syntax.
  // JSON permits literal LS/PS inside strings; the TypeScript scanner treats
  // them as source line terminators. Escape these equivalent JSON characters.
  const tree = ts.parseJsonText('request.json', text.replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029'));
  function visit(node) {
    if (ts.isObjectLiteralExpression(node)) {
      const names = new Set();
      for (const property of node.properties) {
        const name = property.name.text;
        if (names.has(name)) throw new Error('duplicate');
        names.add(name);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(tree);
  return value;
}

if (process.argv[2] === '--probe') {
  process.stdout.write(JSON.stringify(probe));
} else {
  try {
    if (process.argv[2] !== '--analyze' || !pinned) throw new Error('unsupported');
    const bytes = fs.readFileSync(0);
    if (bytes.length > 2000000) throw new Error('unsupported');
    const request = strictRequest(bytes);
    const keys = ['dialect', 'language', 'path', 'protocol_version', 'source'];
    if (!request || typeof request !== 'object' || Array.isArray(request)
      || JSON.stringify(Object.keys(request).sort()) !== JSON.stringify(keys)
      || request.protocol_version !== '1' || request.dialect !== null
      || !['typescript', 'javascript'].includes(request.language)
      || typeof request.source !== 'string' || request.source.includes('\0')
      || typeof request.path !== 'string' || /[\\:\x00-\x1f]/.test(request.path)
      || request.path.split('/').some(part => ['', '.', '..', '.git'].includes(part))) throw new Error('unsupported');
    const extension = request.path.split('.').pop().toLowerCase();
    const typescript = ['ts', 'tsx', 'mts', 'cts'].includes(extension);
    const javascript = ['js', 'jsx', 'mjs', 'cjs'].includes(extension);
    if ((request.language === 'typescript' && !typescript) || (request.language === 'javascript' && !javascript)) {
      output(false, [], 'UNSUPPORTED_SOURCE');
    } else {
      const diagnostics = [];
      const fixturePath = /(^|\/)(__tests__|tests?|fixtures?|__mocks__)(\/|$)|\.(test|spec)\.[cm]?[jt]sx?$/i.test(request.path);
      const configPath = /(^|\/)(config|configuration|environments?)(\/|$)|(^|\/)(environment(?:\.[^/]*)?|[^/]*\.config)\.[cm]?[jt]s$/i.test(request.path);
      const literal = node => node && node.type === 'Literal' && typeof node.value === 'string' ? node.value : null;
      const keyName = node => node && (node.type === 'Identifier' ? node.name : literal(node));
      const credentialName = name => typeof name === 'string' && /^(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|client[_-]?secret|secret[_-]?key|private[_-]?key)$/i.test(name);
      const placeholder = value => /^(?:|example|sample|dummy|placeholder|changeme|replace[_-]?me|your[_-].*|<[^>]+>|\$\{[^}]+\})$/i.test(value.trim());
      const contextRules = {
        meta: { type: 'problem', schema: [], messages: { issue: 'Literal runtime configuration.' } },
        create(context) {
          function emit(rule_id, node) {
            diagnostics.push({ rule_id, region: region(request.source, node) });
            context.report({ node, messageId: 'issue' });
          }
          function secret(name, value, node) {
            const text = literal(value);
            if (credentialName(name) && text !== null && !placeholder(text)) emit('HC002', node);
          }
          function variable(node, name) {
            let scope = context.sourceCode.getScope(node);
            while (scope) {
              const found = scope.set.get(name);
              if (found) return found;
              scope = scope.upper;
            }
            return null;
          }
          function networkCall(node) {
            const callee = node.callee;
            if (callee.type === 'Identifier' && callee.name === 'fetch') {
              const found = variable(node, 'fetch');
              return !found || (found.defs.length === 0 && !found.references.some(ref => ref.isWrite()));
            }
            if (callee.type !== 'MemberExpression' || callee.computed || callee.object.type !== 'Identifier'
              || !['get', 'post', 'put', 'patch', 'delete', 'request'].includes(callee.property.name)) return false;
            const found = variable(node, callee.object.name);
            return !!found && !found.references.some(ref => ref.isWrite()) && found.defs.some(def => def.type === 'ImportBinding'
              && def.node.type === 'ImportDefaultSpecifier' && def.parent.source.value === 'axios');
          }
          return {
            VariableDeclarator(node) { if (node.id.type === 'Identifier') secret(node.id.name, node.init, node); },
            AssignmentExpression(node) {
              const name = node.left.type === 'Identifier' ? node.left.name
                : node.left.type === 'MemberExpression' && (!node.left.computed || literal(node.left.property) !== null)
                  ? keyName(node.left.property) : null;
              secret(name, node.right, node);
            },
            Property(node) { if (!node.method && node.kind === 'init' && (!node.computed || literal(node.key) !== null)) secret(keyName(node.key), node.value, node); },
            PropertyDefinition(node) { if (!node.computed || literal(node.key) !== null) secret(keyName(node.key), node.value, node); },
            CallExpression(node) {
              const endpoint = literal(node.arguments[0]);
              if (!fixturePath && !configPath && endpoint !== null && /^https?:\/\/[^\s/]+/i.test(endpoint)
                && networkCall(node)) emit('HC001', node.arguments[0]);
            },
          };
        },
      };
      const emptyCatch = {
        meta: { type: 'problem', schema: [], messages: { issue: 'Empty catch block.' } },
        create(context) {
          return { CatchClause(node) {
            if (node.body.body.length === 0) {
              diagnostics.push({ rule_id: 'LOG002', region: region(request.source, node) });
              context.report({ node, messageId: 'issue' });
            }
          } };
        },
      };
      const linter = new Linter({ configType: 'flat' });
      const messages = linter.verify(request.source, [{
        files: ['**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs}'],
        languageOptions: { parser, ecmaVersion: 'latest', sourceType: 'module',
          parserOptions: { project: false, projectService: false, tsconfigRootDir: __dirname,
            ecmaFeatures: { jsx: true } } },
        plugins: { devsift: { rules: { 'empty-catch': emptyCatch, 'runtime-context': contextRules } } },
        rules: { 'devsift/empty-catch': 'error', 'devsift/runtime-context': 'error' },
      }], { filename: request.path, allowInlineConfig: false });
      const parseFailure = messages.some(message => message.fatal);
      if (parseFailure) output(false, [], 'PARSE_ERROR');
      else if (diagnostics.length > 1000) output(false, diagnostics.slice(0, 1000));
      else output(true, diagnostics, 'COMPLETED');
    }
  } catch (_error) {
    output(false);
  }
}
