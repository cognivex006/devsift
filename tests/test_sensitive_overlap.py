"""A verified full-span mask must survive every rule's source reproof."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.adapters import AdapterCapability
from devsift.baseline import capture_entry
from devsift.evidence import Region, verify_source
from devsift.git_changes import classify
from devsift.scanner import AdapterOutcome, ScanFinding, scan


class SensitiveOverlapTests(unittest.TestCase):
    def test_nonsecurity_mask_survives_scan_classifier_and_baseline_with_raw_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git('init', '-q')
            fingerprints = []
            for secret in ['abcd' * 10, 'efgh' * 10]:
                text = 'AWS_SECRET_ACCESS_KEY="' + secret + '"'
                (root / 'code.py').write_text(text, encoding='utf-8')
                git('add', 'code.py')
                git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
                sha = git('rev-parse', 'HEAD')
                source = verify_source(root, 'local', sha, 'code.py', Region(1, 1, 1, len(text)+1), sensitive=True)
                class Provider:
                    capability = AdapterCapability('overlapping-rule', '1', ('python',), True)
                    def analyze(self, target):
                        return AdapterOutcome(True, (ScanFinding('CASE-OVERLAP', 'LOG001', source),))
                before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                record = scan(root, adapters=(Provider(),))
                self.assertEqual(record['findings'][0]['source']['before'], '[REDACTED]')
                self.assertNotIn(secret, json.dumps(record))
                proof = classify(root, sha, sha, 'LOG001', source)
                self.assertEqual(proof.lifecycle_class, 'LEGACY_UNCHANGED')
                entry = capture_entry(root, 'LOG001', '1', source)
                fingerprints.append(entry.fingerprint)
                after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(before, after)
            self.assertNotEqual(*fingerprints)
