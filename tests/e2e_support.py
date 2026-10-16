"""Shared real-process E2E fixtures, never an analyzer/classifier replacement.

Native opt-in explicitly trusts already-built DevSift helpers, not target code.
Overrides match the existing native suite. Setup is separate from scanning.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from devsift.dotnet_adapter import make_tool as dotnet_tool
from devsift.go_adapter import make_tool as go_tool
from devsift.native_host import probe_tool
from devsift.native_manifest import ConfiguredTool, manifest_bytes
from devsift.sql_adapter import make_tool as sql_tool
from devsift.typescript_adapter import make_tool as frontend_tool

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ENABLED = os.environ.get('DEVSIFT_TEST_NATIVE') == '1'


def environment():
    # Fixture commits/scans must not inherit consumer Git hooks, filters or refs.
    result = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    result.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                  GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0',
                  GIT_NO_REPLACE_OBJECTS='1', GIT_NO_LAZY_FETCH='1',
                  PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
    return result


def native_tools(*languages):
    """Fail, rather than skip, if opted-in real helpers cannot probe."""
    tools = {}
    for language in languages:
        if language in {'csharp', 'sql'}:
            runtime = os.environ.get('DEVSIFT_DOTNET_EXECUTABLE') or shutil.which('dotnet')
            if not runtime:
                raise AssertionError('Native E2E requires an explicitly available .NET runtime')
            variable, directory = (('DEVSIFT_ROSLYN_ARTIFACT_DIR', 'dotnet') if language == 'csharp'
                                   else ('DEVSIFT_SQL_ARTIFACT_DIR', 'sql'))
            artifacts = Path(os.environ.get(variable, ROOT / '.devsift/local/tools' / directory)).resolve()
            factory = dotnet_tool if language == 'csharp' else sql_tool
            tool = factory(str(Path(runtime).resolve()), artifacts)
        elif language == 'go':
            executable = os.environ.get('DEVSIFT_GO_ARTIFACT', str(
                ROOT / '.devsift/local/tools/go' / ('devsift-go.exe' if os.name == 'nt' else 'devsift-go')))
            tool = go_tool(str(Path(executable).resolve()))
        elif language == 'typescript':
            executable = os.environ.get('DEVSIFT_NODE_EXECUTABLE') or shutil.which('node')
            if not executable:
                raise AssertionError('Native E2E requires an explicitly available Node runtime')
            package = Path(os.environ.get('DEVSIFT_FRONTEND_PACKAGE', ROOT / 'native/frontend')).resolve()
            tool = frontend_tool(str(Path(executable).resolve()), package)
        else:
            raise AssertionError('Unsupported E2E tool language')
        probe = probe_tool(tool)
        if not probe.available:
            raise AssertionError('Requested real native E2E probe failed: ' + tool.tool_id + ': ' + probe.reason)
        tools[language] = tool
    return tools


def snapshot(root):
    """Includes source, baseline, Git objects/index/config and newly created dirs."""
    return {path.relative_to(root).as_posix(): None if path.is_dir() else hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob('*')}


class Repository:
    def __init__(self, parent, sources):
        self.parent = parent
        self.root = parent / 'consumer'
        self.root.mkdir()
        self.git('init', '-q')
        for key, value in [('user.name', 'DevSift E2E Fixture'), ('user.email', 'e2e@example.invalid'),
                           ('core.autocrlf', 'false'), ('core.hooksPath', str(parent / 'no-hooks')),
                           ('core.attributesFile', os.devnull), ('commit.gpgSign', 'false')]:
            self.git('config', key, value)
        for name, content in sources.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.commit('synthetic consumer fixture')

    def git(self, *arguments):
        return subprocess.run(['git', '-C', str(self.root), *arguments], env=environment(),
                              capture_output=True, check=True, timeout=20).stdout.decode('utf-8').strip()

    def commit(self, message):
        self.git('add', '--all')
        self.git('commit', '-qm', message)
        self.head = self.git('rev-parse', 'HEAD')
        return self.head

    def manifest(self, tools, *, dialect='tsql160'):
        configured = tuple(ConfiguredTool(tool, dialect if language == 'sql' else None)
                           for language, tool in tools.items())
        raw = manifest_bytes(configured)
        path = self.parent / 'explicit-native-manifest.json'
        path.write_bytes(raw)
        return path.resolve(), hashlib.sha256(raw).hexdigest()

    def cli(self, manifest, digest, *, all_scope=True):
        arguments = [sys.executable, '-B', '-m', 'devsift', 'scan', '--all' if all_scope else '--changed',
                     '--native-manifest', str(manifest), '--native-manifest-digest', digest]
        process = subprocess.run(arguments, cwd=self.root, env=environment(), capture_output=True,
                                 text=True, encoding='utf-8', timeout=90)
        if process.stderr:
            raise AssertionError('Public CLI emitted stderr: ' + process.stderr)
        record = json.loads(process.stdout)
        if process.returncode != record['exit_code']:
            raise AssertionError('CLI process/envelope exit mismatch')
        return record


@contextmanager
def repository(sources):
    with tempfile.TemporaryDirectory(prefix='devsift-e2e-') as directory:
        yield Repository(Path(directory), sources)


def assert_public_record(case, record):
    case.assertEqual(set(record), {'schema_version', 'command', 'status', 'exit_code', 'complete',
                                  'enforced_count', 'findings', 'errors', 'data'})
    case.assertEqual(record['schema_version'], '1.0')
    case.assertEqual(record['command'], 'scan')
    for finding in record['findings']:
        case.assertEqual(set(finding), {'case_id', 'rule_id', 'message', 'path', 'source', 'severity',
                                       'lifecycle_class', 'enforcement', 'security_escalation'})
        case.assertEqual(finding['lifecycle_class'], 'UNKNOWN')
        case.assertEqual(finding['enforcement'], 'incomplete')
