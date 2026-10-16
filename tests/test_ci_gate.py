"""Fresh real-process/Git CI gates; fixtures are explicit trusted test analyzers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from devsift.ci_gate import CiError, GateConfig, run_ci
from devsift.native_host import ToolDefinition, file_digest
from devsift.native_manifest import ConfiguredTool, manifest_bytes
from devsift.process_runner import ProcessSpec

ROOT = Path(__file__).resolve().parents[1]


class CiGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'source'
        self.root.mkdir()
        self.helper = self.directory / 'trusted_fixture.py'
        self.helper.write_text(textwrap.dedent('''
            import ast,json,sys
            identity={'protocol_version':'1','tool_id':'ci-python-fixture','tool_version':'1'}
            if sys.argv[-1]=='--probe':
                print(json.dumps(dict(identity,languages=['python'],engine_versions={})))
            else:
                request=json.load(sys.stdin);source=request['source'];findings=[]
                try:
                    tree=ast.parse(source)
                    for node in ast.walk(tree):
                        rule=None
                        if isinstance(node,ast.ExceptHandler) and len(node.body)==1 and isinstance(node.body[0],ast.Pass):rule='LOG002'
                        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='print':rule='LOG001'
                        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) and node.value.value.startswith('gh'+'p_') and len(node.value.value)==40:rule='HC002'
                        if rule:
                            lines=source.split('\\n')
                            start=len(lines[node.lineno-1].encode()[:node.col_offset].decode())+1
                            end=len(lines[node.end_lineno-1].encode()[:node.end_col_offset].decode())+1
                            findings.append({'rule_id':rule,'region':{'start_line':node.lineno,'start_column':start,'end_line':node.end_lineno,'end_column':end}})
                    print(json.dumps(dict(identity,complete=True,diagnostics=findings,reason='COMPLETED',metadata={})))
                except SyntaxError:
                    print(json.dumps(dict(identity,complete=False,diagnostics=[],reason='PARSE_ERROR',metadata={})))
        '''), encoding='utf-8')
        self.tool = ToolDefinition('ci-python-fixture', '1', ('python',),
                                   ProcessSpec(str(Path(sys.executable).resolve()), ('-I', '-B', str(self.helper))),
                                   file_digest(sys.executable), ((str(self.helper), file_digest(self.helper)),), ())
        self.manifest = self.directory / 'manifest.json'
        self.configure((ConfiguredTool(self.tool),))
        self.git('init', '-q')
        (self.root / 'README.md').write_text('fixture\n')
        self.git('add', 'README.md')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD')

    def configure(self, tools):
        raw = manifest_bytes(tools)
        self.manifest.write_bytes(raw)
        self.digest = hashlib.sha256(raw).hexdigest()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self):
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')

    def source(self, text):
        (self.root / 'code.py').write_bytes(text.encode())
        self.git('add', 'code.py')
        self.commit()

    def run_gate(self, **kwargs):
        return run_ci(self.root, native_manifest=self.manifest, native_manifest_digest=self.digest,
                      paths=('code.py',), **kwargs)

    def test_actual_clean_scan_and_cli_are_read_only_and_fresh(self):
        marker = self.directory / 'must-not-execute'
        self.source('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("bad")\n')
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        outcome = self.run_gate()
        self.assertEqual(outcome.exit_code, 0)
        changed = outcome.to_dict(); changed['status'] = 'other'
        self.assertEqual(outcome.to_dict()['status'], 'clean')
        invocation = subprocess.run([sys.executable, '-B', '-m', 'devsift', 'ci', '--paths', 'code.py',
                                     '--native-manifest', str(self.manifest), '--native-manifest-digest', self.digest],
                                    cwd=self.root, env=dict(os.environ, PYTHONPATH=str(ROOT)), capture_output=True, text=True)
        self.assertEqual(invocation.returncode, 0, invocation.stderr)
        self.assertEqual(json.loads(invocation.stdout)['command'], 'ci')
        self.assertFalse(marker.exists())
        after = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_new_error_blocks_unknown_stays_incomplete_and_legacy_is_advisory(self):
        self.source('try:\n    work()\nexcept:\n    pass\n')
        new = self.run_gate(base_ref=self.base)
        self.assertEqual(new.exit_code, 1)
        self.assertEqual(new.scan_record()['findings'][0]['lifecycle_class'], 'NEW')
        self.assertEqual(self.run_gate().exit_code, 2)
        legacy = self.run_gate(base_ref='HEAD')
        self.assertEqual(legacy.exit_code, 0)
        self.assertEqual(legacy.scan_record()['findings'][0]['enforcement'], 'advisory')

    def test_supported_threshold_is_applied_before_policy_gating(self):
        self.source('try:\n    work()\nexcept:\n    pass\n')
        self.assertEqual(self.run_gate(base_ref=self.base).exit_code, 1)
        critical_only = self.run_gate(base_ref=self.base, config=GateConfig('Critical'))
        self.assertEqual(critical_only.exit_code, 0)
        self.assertEqual(critical_only.to_dict()['data']['quality_gate']['minimum_severity'], 'Critical')

    def test_changed_region_without_baseline_absence_is_not_assumed_introduced(self):
        self.source('def f():\n    return 1\n')
        base = self.git('rev-parse', 'HEAD')
        self.source('def f():\n    try:\n        work()\n    except:\n        pass\n')
        record = self.run_gate(base_ref=base)
        self.assertEqual(record.exit_code, 2)
        self.assertEqual(record.to_dict()['findings'][0]['lifecycle_class'], 'UNKNOWN')

    def test_legacy_security_needs_review_without_quality_legacy_block_or_raw_value(self):
        secret = 'gh' + 'p_' + 'a' * 36
        self.source('apiKey=' + repr(secret) + '\n')
        outcome = self.run_gate(base_ref='HEAD')
        self.assertEqual(outcome.scan_record()['exit_code'], 0)
        self.assertEqual(outcome.exit_code, 2)
        self.assertEqual(outcome.to_dict()['enforced_count'], 0)
        self.assertTrue(outcome.to_dict()['findings'][0]['security_escalation'])
        self.assertNotIn(secret, json.dumps(outcome.to_dict()))
        self.assertEqual(outcome.to_dict()['errors'][-1]['code'], 'SECURITY_REVIEW_REQUIRED')

    def test_dirty_or_untracked_clean_bytes_never_hide_head_source(self):
        self.source('try:\n    work()\nexcept:\n    pass\n')
        (self.root / 'code.py').write_text('x=1\n')
        self.assertEqual(self.run_gate(base_ref=self.base).exit_code, 2)
        (self.root / 'untracked.py').write_text('x=1\n')
        result = run_ci(self.root, native_manifest=self.manifest, native_manifest_digest=self.digest,
                        paths=('untracked.py',))
        self.assertEqual(result.exit_code, 2)

    def test_missing_tool_even_unused_or_tampered_manifest_stays_incomplete(self):
        self.source('x=1\n')
        missing = self.directory / 'missing.exe'
        tool = ToolDefinition('missing-fixture', '1', ('go',), ProcessSpec(str(missing)),
                              '0' * 64, ((str(missing), '0' * 64),), ())
        self.configure((ConfiguredTool(self.tool), ConfiguredTool(tool)))
        outcome = self.run_gate()
        self.assertEqual(outcome.exit_code, 2)
        self.assertIn('NATIVE_TOOL_UNAVAILABLE', [error['code'] for error in outcome.to_dict()['errors']])
        self.manifest.write_bytes(self.manifest.read_bytes() + b' ')
        self.assertEqual(self.run_gate().exit_code, 2)

    def test_parse_failure_bad_git_and_cli_misuse_never_echo_inputs(self):
        self.source('privateFixture =\n')
        outcome = self.run_gate(base_ref=self.base)
        self.assertEqual(outcome.exit_code, 2)
        self.assertNotIn('privateFixture', json.dumps(outcome.to_dict()))
        self.assertEqual(self.run_gate(base_ref='missing-private-ref').exit_code, 2)
        for args in [['ci'], ['ci', '--minimum-severity', 'private-value'],
                     ['ci', '--native-manifest', 'relative-private-path', '--native-manifest-digest', '0'*64]]:
            completed = subprocess.run([sys.executable, '-B', '-m', 'devsift', *args], cwd=ROOT,
                                       capture_output=True, text=True)
            self.assertEqual(completed.returncode, 3)
            self.assertEqual(completed.stdout, '')
            self.assertNotIn('private-', completed.stderr)

    def test_gate_configuration_uses_strict_types(self):
        for args in [(True,), ('private',), ('Warning',), ('Error', 1)]:
            with self.assertRaises(CiError): GateConfig(*args)
