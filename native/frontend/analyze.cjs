'use strict';

const fs = require('node:fs');
const { Linter } = require('eslint');
const parser = require('@typescript-eslint/parser');
const ts = require('typescript');
const TOOL_ID = 'devsift-typescript';
const TOOL_VERSION = '1.2.0';
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
          const mutatedRoots = new Set();
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
          function unshadowed(node, name) {
            if (mutatedRoots.has(name)) return false;
            const found = variable(node, name);
            if (found && (found.defs.length || found.references.some(ref => ref.isWrite()))) return false;
            let scope = context.sourceCode.getScope(node);
            while (scope) {
              if (scope.through.some(ref => ref.identifier.name === name && ref.isWrite())) return false;
              scope = scope.upper;
            }
            return true;
          }
          function signature(value, name = '') {
            if (typeof value !== 'string') return false;
            if (/^(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{50,255})$/.test(value)) return true;
            if (['awssecretaccesskey', 'secretaccesskey'].includes(name.replace(/_/g, '').toLowerCase())
              && /^[A-Za-z0-9/+=]{40}$/.test(value) && !/EXAMPLE|YOUR/i.test(value)) return true;
            const text = value.trim();
            for (const label of ['PRIVATE KEY', 'RSA PRIVATE KEY', 'EC PRIVATE KEY', 'OPENSSH PRIVATE KEY']) {
              const header = `-----BEGIN ${label}-----`, footer = `-----END ${label}-----`;
              if (!text.startsWith(header)) continue;
              if (!text.endsWith(footer)) return false;
              const body = text.slice(header.length, -footer.length);
              if (body.length < 32 || body.length > 65536) return false;
              let count = 0;
              for (const char of body) {
                if (/[A-Za-z0-9+/=]/.test(char)) count++;
                else if (!/\s/.test(char)) return false;
              }
              return count >= 32;
            }
            return false;
          }
          function sensitiveValue(node) {
            if (signature(literal(node))) return true;
            if (!node || node.type !== 'Identifier') return false;
            const found = variable(node, node.name);
            if (!found || found.defs.length !== 1 || mutatedRoots.has(node.name)
              || found.references.some(ref => ref.isWrite() && !ref.init)
              || found.scope.variableScope !== context.sourceCode.getScope(node).variableScope) return false;
            const definition = found.defs[0];
            return definition.type === 'Variable' && definition.node.type === 'VariableDeclarator'
              && definition.node.id.type === 'Identifier' && signature(literal(definition.node.init), definition.node.id.name);
          }
          function imported(node, identifier) {
            const found = variable(node, identifier.name);
            if (!found || mutatedRoots.has(identifier.name) || found.references.some(ref => ref.isWrite())) return null;
            const definitions = found.defs.filter(def => def.type === 'ImportBinding');
            if (definitions.length !== 1) return null;
            const definition = definitions[0];
            return { module: definition.parent.source.value.replace(/^node:/, ''),
              name: definition.node.type === 'ImportSpecifier' ? keyName(definition.node.imported)
                : ['ImportDefaultSpecifier', 'ImportNamespaceSpecifier'].includes(definition.node.type) ? '*' : null };
          }
          function tlsSink(node) {
            const callee = node.callee;
            let reference, method;
            if (callee.type === 'Identifier') {
              reference = imported(node, callee); method = reference?.name;
            } else if (callee.type === 'MemberExpression' && !callee.computed && callee.object.type === 'Identifier') {
              reference = imported(node, callee.object); method = callee.property.name;
              if (reference?.name !== '*') return false;
            } else return false;
            const recognized = node.type === 'NewExpression'
              ? reference?.module === 'https' && method === 'Agent'
              : reference?.module === 'https' && ['get', 'request'].includes(method)
                || reference?.module === 'tls' && method === 'connect';
            if (!recognized) return false;
            const options = node.arguments.find(argument => argument.type === 'ObjectExpression');
            if (!options || options.properties.some(property => property.type !== 'Property'
              || property.computed && literal(property.key) === null)) return false;
            const matches = options.properties.filter(property => keyName(property.key) === 'rejectUnauthorized');
            const effective = matches.at(-1);
            return !!effective && !effective.method && effective.kind === 'init'
              && effective.value.type === 'Literal' && effective.value.value === false;
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
            Program(node) {
              const stack = [node];
              while (stack.length) {
                const current = stack.pop();
                if ((current.type === 'AssignmentExpression' || current.type === 'UpdateExpression')
                  && (current.left || current.argument)?.type === 'MemberExpression') {
                  const target = current.left || current.argument;
                  if (target.object.type === 'Identifier') mutatedRoots.add(target.object.name);
                }
                for (const key of context.sourceCode.visitorKeys[current.type] || []) {
                  const value = current[key];
                  if (Array.isArray(value)) { for (const child of value) if (child?.type) stack.push(child); }
                  else if (value?.type) stack.push(value);
                }
              }
            },
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
              const callee = node.callee;
              if (callee.type === 'MemberExpression' && !callee.computed && callee.object.type === 'Identifier'
                && callee.object.name === 'console' && unshadowed(node, 'console')
                && ['log', 'info', 'warn', 'error', 'debug', 'trace'].includes(callee.property.name)
                && node.arguments.some(argument => sensitiveValue(argument))) emit('SEC001', node);
              if (tlsSink(node)) emit('SEC002', node);
              const endpoint = literal(node.arguments[0]);
              if (!fixturePath && !configPath && endpoint !== null && /^https?:\/\/[^\s/]+/i.test(endpoint)
                && networkCall(node)) emit('HC001', node.arguments[0]);
            },
            NewExpression(node) { if (tlsSink(node)) emit('SEC002', node); },
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
