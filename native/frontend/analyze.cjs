'use strict';

const fs = require('node:fs');
const { Linter } = require('eslint');
const parser = require('@typescript-eslint/parser');
const TOOL_ID = 'devsift-typescript';
const TOOL_VERSION = '1.0.0';
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

if (process.argv[2] === '--probe') {
  process.stdout.write(JSON.stringify(probe));
} else {
  try {
    if (process.argv[2] !== '--analyze' || !pinned) throw new Error('unsupported');
    const bytes = fs.readFileSync(0);
    if (bytes.length > 2000000) throw new Error('unsupported');
    const request = JSON.parse(bytes.toString('utf8'));
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
        plugins: { devsift: { rules: { 'empty-catch': emptyCatch } } },
        rules: { 'devsift/empty-catch': 'error' },
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
