"""CLI doctor integration: real subprocesses with untrusted target files present."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DoctorCliTests(unittest.TestCase):
    def invoke(self, *args, cwd):
        return subprocess.run([sys.executable, '-B', '-m', 'devsift', 'doctor', *args],
                              cwd=cwd, env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1'),
                              capture_output=True, text=True, timeout=30)

    def test_default_doctor_does_not_trust_or_mutate_project_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'.devsift').mkdir()
            (root/'.devsift/tools.json').write_text('{"private":"untrustedTargetValue"}')
            before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
            process=self.invoke(cwd=root)
            self.assertEqual(process.returncode,2,process.stderr)
            record=json.loads(process.stdout)
            self.assertEqual(record['command'],'doctor')
            self.assertFalse(record['complete'])
            self.assertFalse(record['data']['analysis_performed'])
            self.assertIn('providers',record['data'])
            self.assertNotIn('untrustedTargetValue',process.stdout+process.stderr)
            self.assertEqual(before,{str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_manifest_options_must_be_paired_absolute_and_digest_shaped(self):
        with tempfile.TemporaryDirectory() as directory:
            for args in [('--native-manifest','privateRelativeValue'),
                         ('--native-manifest-digest','a'*64),
                         ('--native-manifest','privateRelativeValue','--native-manifest-digest','a'*64),
                         ('--native-manifest',str(Path(directory)/'tools.json'),'--native-manifest-digest','PRIVATE')]:
                with self.subTest(args=args):
                    process=self.invoke(*args,cwd=directory)
                    self.assertEqual(process.returncode,3,process.stdout)
                    self.assertEqual(json.loads(process.stderr)['status'],'misuse')
                    self.assertNotIn('privateRelativeValue',process.stdout+process.stderr)
                    self.assertNotIn('PRIVATE',process.stdout+process.stderr)

    def test_explicit_unavailable_manifest_is_safe_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'privateMissingManifest.json'
            process=self.invoke('--native-manifest',str(path),'--native-manifest-digest','a'*64,cwd=directory)
            self.assertEqual(process.returncode,2,process.stderr)
            self.assertFalse(json.loads(process.stdout)['complete'])
            self.assertNotIn('privateMissingManifest',process.stdout+process.stderr)


if __name__=='__main__': unittest.main()
