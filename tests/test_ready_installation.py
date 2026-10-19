"""A fresh ordinary installation must actually lint and deliver a human report."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_INSTALLER_BUNDLE'), 'explicit real ready-installer bundle required')
class ReadyInstallationTests(unittest.TestCase):
    def test_fresh_install_then_plain_scan_finds_all_four_language_issues_without_sdks(self):
        archive = Path(os.environ['DEVSIFT_TEST_INSTALLER_BUNDLE']).resolve()
        git = shutil.which('git')
        self.assertTrue(git, 'Git required for immutable source proof')
        temporary_directory = tempfile.TemporaryDirectory(prefix='devsift-ready-install-')
        with temporary_directory as temporary:
            if os.name == 'nt':
                temporary_directory.name = '\\\\?\\' + temporary
            root = Path(temporary)
            home, bundle, source = root / 'new user', root / 'bundle', root / 'project'
            home.mkdir(); bundle.mkdir(); source.mkdir()
            home, bundle, source = home.resolve(), bundle.resolve(), source.resolve()
            with zipfile.ZipFile(archive) as supplied:
                self.assertTrue(any(name.startswith('analyzers/') and name.endswith('.zip') for name in supplied.namelist()))
                supplied.extractall(bundle)
            environment = {key: value for key, value in os.environ.items()
                           if key.upper() not in {'PYTHONPATH', 'PYTHONHOME', 'DOTNET_ROOT', 'NODE_PATH'}
                           and not key.upper().startswith(('GIT_', 'PIP_'))}
            environment.update(HOME=str(home), USERPROFILE=str(home), GIT_CONFIG_GLOBAL=os.devnull,
                               GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM='1',
                               PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                               PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
            # The installed CLI's private Python and the four bundled runtimes
            # use absolute paths. Keep only Git and essential OS executables.
            paths = [str(Path(git).parent)]
            if os.name == 'nt':
                paths += [str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot']]
            else:
                paths += ['/usr/bin', '/bin']
            environment['PATH'] = os.pathsep.join(dict.fromkeys(paths))

            def run(args, cwd, allowed=(0,), timeout=300):
                result = subprocess.run(args, cwd=cwd, env=environment, capture_output=True,
                                        encoding='utf-8', timeout=timeout)
                self.assertIn(result.returncode, allowed, (result.stdout + result.stderr)[-3000:])
                return result

            installed = run([sys.executable, '-I', '-B', str(bundle / 'install.py'), '--home', str(home),
                             '--progress', 'json'], root)
            events = [json.loads(line) for line in installed.stdout.splitlines()]
            self.assertEqual(events[-1]['type'], 'complete')
            state = events[-1]['state']
            self.assertTrue(state['analysis_ready'])
            self.assertEqual(len(state['registered_tools']), 4)
            registry = json.loads((home / '.local/share/devsift/analyzers.json').read_text(encoding='utf-8'))
            manifest = json.loads(Path(registry['manifest']).read_text(encoding='utf-8'))
            self.assertEqual(len(manifest['tools']), 4)
            self.assertTrue(all(Path(entry['definition']['process']['executable']).resolve().is_relative_to(home.resolve())
                                for entry in manifest['tools']))
            launcher = state['launcher']
            samples = {
                'a.cs': 'using System; class C { static void Main(){ Console.WriteLine(1); } }\n',
                'a.go': 'package main\nimport "fmt"\nfunc main(){fmt.Println(1)}\n',
                'a.sql': "DECLARE @q nvarchar(max)=N'SELECT * FROM dbo.T WHERE id=' + @input; EXEC(@q);\n",
                'a.js': 'try {} catch {}\n',
            }
            for name, value in samples.items():
                (source / name).write_bytes(value.encode())
            for args in (('init', '-q'), ('config', 'core.autocrlf', 'false'), ('add', '--all'),
                         ('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                          '-c', 'commit.gpgSign=false', 'commit', '-qm', 'fixture')):
                run([git, *args], source)
            before = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in source.rglob('*') if p.is_file()}
            scan = run([launcher, 'scan', '--all', '--legacy-mode', 'recommend', '--summary',
                        '--report-language', 'th'], source, allowed=(0, 1, 2))
            self.assertEqual(scan.stderr, '')
            result = json.loads(scan.stdout)
            if 'counts' not in result.get('data', {}):
                diagnostic = '''import sys,traceback
from devsift import cli,scan_store
actual=scan_store.run_streamed
def diagnosed(*args,**kwargs):
 try: return actual(*args,**kwargs)
 except BaseException:
  traceback.print_exc()
  raise
scan_store.run_streamed=diagnosed
raise SystemExit(cli.main(sys.argv[1:]))
'''
                details = run([state['python'], '-I', '-B', '-c', diagnostic,
                               'scan', '--all', '--summary', '--report-language', 'th'], source, allowed=(0, 1, 2))
                self.fail('Ordinary scan failed: ' + json.dumps(result) + '\n' + details.stderr[-5000:])
            self.assertEqual(result['data']['counts']['executed'], 4)
            self.assertEqual(result['data']['finding_count'], 4)
            self.assertTrue(result['data']['report_bundle']['reports_complete'])
            self.assertNotIn('NO_AVAILABLE_ANALYZER', {e['code'] for e in result['errors']})
            human = Path(result['data']['report_bundle']['report'])
            self.assertTrue(human.is_file())
            text = human.read_text(encoding='utf-8')
            self.assertTrue(any('\u0e00' <= char <= '\u0e7f' for char in text))
            for name in samples:
                self.assertIn(name, text)
            for rule in ('LOG001', 'LOG002', 'SEC003'):
                self.assertIn(rule, text)
            index = json.loads(Path(result['data']['report_bundle']['index']).read_text(encoding='utf-8'))
            cases = []
            for page in index['pages']:
                for item in page['files']:
                    if item['file'].endswith('/findings.json'):
                        cases += json.loads((Path(result['data']['report_bundle']['index']).parent / item['file']).read_text(encoding='utf-8'))['cases']
            self.assertEqual(len(cases), 4)
            self.assertTrue(all(case['source']['status'] == 'VERIFIED' for case in cases))
            after = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in source.rglob('*') if p.is_file()}
            self.assertEqual(before, after)
            proof = os.environ.get('DEVSIFT_TEST_READY_RECEIPT')
            if proof:
                Path(proof).write_text(json.dumps({'ordinary_install': True, 'native_flags_on_scan': False,
                    'sdks_required': False, 'analyzers_executed': 4, 'findings': 4, 'verified_source_cases': 4,
                    'reports_complete': True, 'thai_report': True, 'target_modified': False}, indent=2), encoding='utf-8')
