"""Actual standalone wrapper with a controlled kit and real Git/process/proof."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

from devsift.native_host import ToolDefinition, file_digest
from devsift.native_manifest import ConfiguredTool, manifest_bytes
from devsift.process_runner import ProcessSpec

ROOT = Path(__file__).resolve().parents[1]


class QualityPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.kit = self.directory / 'trusted-kit'
        (self.kit / 'tools').mkdir(parents=True)
        shutil.copytree(ROOT / 'devsift', self.kit / 'devsift', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        self.script = self.kit / 'tools/run_quality_ci.py'
        shutil.copy2(ROOT / 'tools/run_quality_ci.py', self.script)
        helper = self.kit / 'trusted_ast_fixture.py'
        helper.write_text(textwrap.dedent('''
            import ast,json,sys
            identity={'protocol_version':'1','tool_id':'pipeline-python-fixture','tool_version':'1'}
            if sys.argv[-1]=='--probe':
                print(json.dumps(dict(identity,languages=['python'],engine_versions={})))
            else:
                request=json.load(sys.stdin)
                try:
                    tree=ast.parse(request['source']); findings=[]; lines=request['source'].split('\\n')
                    for node in ast.walk(tree):
                        if isinstance(node,ast.ExceptHandler) and len(node.body)==1 and isinstance(node.body[0],ast.Pass):
                            start=len(lines[node.lineno-1].encode()[:node.col_offset].decode())+1
                            end=len(lines[node.end_lineno-1].encode()[:node.end_col_offset].decode())+1
                            findings.append({'rule_id':'LOG002','region':{'start_line':node.lineno,'start_column':start,'end_line':node.end_lineno,'end_column':end}})
                    print(json.dumps(dict(identity,complete=True,diagnostics=findings,reason='COMPLETED',metadata={})))
                except SyntaxError:
                    print(json.dumps(dict(identity,complete=False,diagnostics=[],reason='PARSE_ERROR',metadata={})))
        '''), encoding='utf-8')
        tool = ToolDefinition('pipeline-python-fixture', '1', ('python',),
                              ProcessSpec(str(Path(sys.executable).resolve()), ('-I', '-B', str(helper))),
                              file_digest(sys.executable), ((str(helper), file_digest(helper)),), ())
        cache = self.kit / '.devsift/local'
        cache.mkdir(parents=True)
        raw = manifest_bytes((ConfiguredTool(tool),))
        (cache / 'native-manifest.json').write_bytes(raw)
        (cache / 'native-manifest.sha256').write_text(hashlib.sha256(raw).hexdigest() + '\n', encoding='ascii')
        self.source = self.directory / 'source'
        (self.source / 'devsift').mkdir(parents=True)
        (self.source / 'README.md').write_text('fixture\n', encoding='utf-8')
        self.marker = self.directory / 'TARGET_SOURCE_WAS_EXECUTED'
        (self.source / 'devsift/__init__.py').write_text(
            'from pathlib import Path\nPath(' + repr(str(self.marker)) + ').write_text("bad")\n', encoding='utf-8')
        for args in (('init', '-q'), ('config', 'user.name', 'Fixture'),
                     ('config', 'user.email', 'fixture@example.invalid'), ('config', 'core.autocrlf', 'false'),
                     ('add', 'README.md', 'devsift/__init__.py'), ('commit', '-qm', 'base')):
            self.git(*args)
        self.base = self.git('rev-parse', 'HEAD')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.source), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit_source(self, text):
        (self.source / 'devsift/service.py').write_bytes(text.encode())
        self.git('add', 'devsift/service.py')
        self.git('commit', '-qm', 'source')

    def snapshot(self):
        return {str(p.relative_to(self.source)): None if p.is_dir() else p.read_bytes() for p in self.source.rglob('*')}

    def invoke(self, output, *, base=None, environment_base=None, suppress_bytecode=True):
        env = dict(os.environ)
        env.pop('PYTHONDONTWRITEBYTECODE', None)
        if suppress_bytecode:
            env['PYTHONDONTWRITEBYTECODE'] = '1'
        env.pop('PYTHONPATH', None)
        env.pop('DEVSIFT_BASE_SHA', None)
        if environment_base is not None:
            env['DEVSIFT_BASE_SHA'] = environment_base
        arguments = [sys.executable, *(['-B'] if suppress_bytecode else []), str(self.script),
                     '--repo', str(self.source), '--output', str(output)]
        if base is not None:
            arguments += ['--base', base]
        return subprocess.run(arguments, cwd=self.source, env=env, capture_output=True, text=True, timeout=60)

    def assert_bundle(self, directory):
        self.assertEqual({p.name for p in directory.iterdir()}, {'report.md', 'findings.json', 'results.sarif'})
        return json.loads((directory / 'findings.json').read_text(encoding='utf-8'))

    def test_clean_committed_explicit_scope_outputs_three_files_without_source_execution(self):
        self.commit_source('value = 1\n')
        # Excluded test/helper files must not become implied production coverage.
        (self.source / 'tests').mkdir()
        (self.source / 'tests/ignored.py').write_text('this is not production syntax\n')
        self.git('add', 'tests/ignored.py')
        self.git('commit', '-qm', 'test helper')
        before = self.snapshot()
        output = self.directory / 'clean-output'
        executed = self.invoke(output, base=self.base)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        self.assertEqual(executed.stderr, '')
        self.assertTrue(self.assert_bundle(output)['complete'])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.marker.exists())

    def test_cold_wrapper_without_B_preserves_kit_package_and_source(self):
        self.commit_source('value = 1\n')
        self.assertFalse(list(self.kit.rglob('__pycache__')))
        before_kit = {str(p.relative_to(self.kit)): None if p.is_dir() else p.read_bytes()
                      for p in self.kit.rglob('*')}
        before_source = self.snapshot()
        output = self.directory / 'cold-output'
        executed = self.invoke(output, base=self.base, suppress_bytecode=False)
        self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
        self.assertEqual(before_kit, {str(p.relative_to(self.kit)): None if p.is_dir() else p.read_bytes()
                                      for p in self.kit.rglob('*')})
        self.assertEqual(self.snapshot(), before_source)
        self.assertTrue(self.assert_bundle(output)['complete'])

    def test_new_error_blocks_and_missing_base_keeps_unknown_incomplete(self):
        self.commit_source('try:\n    work()\nexcept Exception:\n    pass\n')
        before = self.snapshot()
        for name, base, expected in (('introduced', self.base, 1), ('unknown', None, 2)):
            with self.subTest(name=name):
                output = self.directory / name
                executed = self.invoke(output, base=base)
                self.assertEqual(executed.returncode, expected, executed.stdout + executed.stderr)
                report = self.assert_bundle(output)
                self.assertEqual(report['exit_code'], expected)
                self.assertEqual(report['cases'][0]['lifecycle_class'], 'NEW' if base else 'UNKNOWN')
                self.assertIn('See the full case report.', executed.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_credential_masks_and_legacy_security_review_remain_incomplete_reports(self):
        private = 'gh' + 'p_' + 'A' * 36  # Non-live credential-shape fixture.
        self.commit_source('api_key = "' + private + '"\n')
        head = self.git('rev-parse', 'HEAD')
        before = self.snapshot()
        for label, base, expected in (('new-secret', self.base, 1), ('legacy-review', head, 2)):
            output = self.directory / label
            executed = self.invoke(output, environment_base=base)
            self.assertEqual(executed.returncode, expected, executed.stdout + executed.stderr)
            report = self.assert_bundle(output)
            self.assertEqual(report['exit_code'], expected)
            for path in output.iterdir():
                self.assertNotIn(private, path.read_text(encoding='utf-8'))
            self.assertNotIn(private, executed.stdout + executed.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_output_inside_source_collision_and_invalid_base_fail_safely(self):
        self.commit_source('value = 1\n')
        before = self.snapshot()
        inside = self.invoke(self.source / 'reports', base=self.base)
        self.assertEqual(inside.returncode, 3)
        self.assertEqual(self.snapshot(), before)
        collision = self.directory / 'occupied'
        collision.mkdir()
        (collision / 'report.md').write_bytes(b'previous')
        executed = self.invoke(collision, base=self.base)
        self.assertIn(executed.returncode, (2, 3))
        self.assertEqual((collision / 'report.md').read_bytes(), b'previous')
        self.assertEqual({p.name for p in collision.iterdir()}, {'report.md'})
        for base in ('0' * 40, 'main', 'private-invalid-base', 'a' * 64):
            rejected = self.invoke(self.directory / 'invalid-base', base=base)
            self.assertEqual(rejected.returncode, 3)
            self.assertNotIn(base, rejected.stdout + rejected.stderr)


if __name__ == '__main__':
    unittest.main()
