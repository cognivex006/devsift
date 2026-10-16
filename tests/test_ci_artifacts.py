"""Artifact ownership/path safety and source-proof-only workflow annotations."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devsift.ci_artifacts import (ArtifactError, _write_artifacts, annotation_lines,
                                 attach_reports, build_reports, write_report_bundle)
from devsift.evidence import Region, verify_source
from devsift.output import result
from devsift.report_model import assemble_report


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / 'source'
        self.root.mkdir()
        self.output = self.directory / 'artifacts'
        self.documents = (('report.md', '# Full report\n'),
                          ('findings.json', json.dumps({'schema_version': '1', 'cases': []})),
                          ('results.sarif', json.dumps({'version': '2.1.0', 'runs': []})))

    def test_explicit_output_is_new_deterministic_and_does_not_write_source(self):
        (self.root / 'keep.txt').write_text('unchanged')
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(_write_artifacts(self.root, self.output, self.documents), ('report.md', 'findings.json', 'results.sarif'))
        self.assertEqual({p.name: p.read_bytes() for p in self.root.iterdir()}, before)
        for name, text in self.documents:
            self.assertEqual((self.output / name).read_bytes(), text.encode())
        with self.assertRaises(ArtifactError): _write_artifacts(self.root, self.output, self.documents)

    def test_source_directory_traversal_names_existing_files_and_links_are_rejected(self):
        for destination in [self.root, self.root / 'reports', Path('relative')]:
            with self.assertRaises(ArtifactError): _write_artifacts(self.root, destination, self.documents)
        bad = (('../report.md', '# bad'), *self.documents[1:])
        with self.assertRaises(ArtifactError): _write_artifacts(self.root, self.output, bad)
        self.output.mkdir()
        (self.output / 'report.md').write_text('user-owned sentinel')
        with self.assertRaises(ArtifactError): _write_artifacts(self.root, self.output, self.documents)
        self.assertEqual((self.output / 'report.md').read_text(), 'user-owned sentinel')
        self.assertFalse((self.output / 'findings.json').exists())

    def test_malformed_duplicate_nonfinite_and_oversized_documents_fail_before_writes(self):
        for json_text in ['{"schema_version":"1","cases":[],"cases":[]}', '{"bad":NaN}', '[]']:
            docs = (self.documents[0], ('findings.json', json_text), self.documents[2])
            with self.assertRaises(ArtifactError): _write_artifacts(self.root, self.output, docs)
            self.assertFalse(self.output.exists())
        docs = (('report.md', 'x' * 16_000_001), *self.documents[1:])
        with self.assertRaises(ArtifactError): _write_artifacts(self.root, self.output, docs)
        self.assertFalse(self.output.exists())

    def test_partial_failure_removes_only_files_created_by_this_call(self):
        self.output.mkdir()
        (self.output / 'unrelated.txt').write_text('keep')
        original = Path.open
        def open_path(path, *args, **kwargs):
            # Windows hosted temp paths may use an 8.3 alias; the sink resolves it.
            if (path.name == 'results.sarif' and path.parent.resolve() == self.output.resolve()
                    and args and args[0] == 'xb'):
                raise PermissionError('private OS message')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', open_path):
            with self.assertRaises(ArtifactError) as error:
                _write_artifacts(self.root, self.output, self.documents)
        self.assertEqual(str(error.exception), 'Report artifacts unavailable')
        self.assertEqual([path.name for path in self.output.iterdir()], ['unrelated.txt'])

    def test_annotations_escape_properties_and_never_echo_code_or_fabricate_location(self):
        def git(*args):
            return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                                  capture_output=True, text=True).stdout.strip()
        git('init', '-q')
        text = 'password="privateValueForArtifactTest"'
        path = 'part%0A,name.py'
        (self.root / path).write_text(text)
        git('add', path)
        git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
        sha = git('rev-parse', 'HEAD')
        source = verify_source(self.root, 'local', sha, path, Region(1, 1, 1, len(text)+1))
        finding = dict(case_id='CASE-1', rule_id='HC001', message='', path=path, source=source.to_dict(),
                       severity='Error', lifecycle_class='NEW', enforcement='block', security_escalation=False)
        record = result('scan', complete=True, findings=[finding], enforced_count=1)
        report = assemble_report(record, repo_root=self.root, trusted_lifecycles=True)
        lines = annotation_lines(report)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('::error file=part%250A%2Cname.py,line=1::'))
        self.assertNotIn('privateValueForArtifactTest', lines[0])
        finding['source']['location']['source_sha'] = 'a' * 40
        unresolved = assemble_report(record, repo_root=self.root, trusted_lifecycles=True)
        line = annotation_lines(unresolved)[0]
        self.assertIn('SOURCE_UNRESOLVED', line)
        self.assertNotIn('file=', line)
        self.assertEqual(annotation_lines(report, limit=0), ())
        with self.assertRaises(ArtifactError): annotation_lines(report, limit=True)

    def test_fresh_ci_reports_preserve_block_incomplete_and_security_review(self):
        # Reuse the explicit trusted AST process fixture, not a mocked scan result.
        from test_ci_gate import CiGateTests
        fixture = CiGateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.source('try:\n    work()\nexcept:\n    pass\n')
        for base, expected in [(fixture.base, 1), (None, 2), ('HEAD', 0)]:
            run = fixture.run_gate(base_ref=base)
            public = attach_reports(run.to_dict(), run.scan_record(), repo_root=fixture.root,
                                    trusted_lifecycles=True)
            self.assertEqual(public['exit_code'], expected, public)
            documents = public['data']['reports']
            self.assertEqual(set(documents), {'json', 'markdown', 'sarif'})
            self.assertEqual(len(documents['json']['cases']), 1)
            self.assertEqual(len(documents['sarif']['runs'][0]['results']), 1)
        secret = 'gh' + 'p_' + 'a' * 36
        fixture.source('apiKey=' + repr(secret) + '\n')
        run = fixture.run_gate(base_ref='HEAD')
        public = attach_reports(run.to_dict(), run.scan_record(), repo_root=fixture.root,
                                trusted_lifecycles=True)
        self.assertEqual(public['exit_code'], 2)
        self.assertFalse(public['complete'])
        self.assertFalse(public['data']['reports']['json']['complete'])
        self.assertFalse(public['data']['reports']['sarif']['runs'][0]['invocations'][0]['executionSuccessful'])
        self.assertNotIn(secret, json.dumps(public))
        report, docs = build_reports(run.scan_record(), repo_root=fixture.root,
                                     trusted_lifecycles=True, formats=('json',))
        self.assertEqual(set(docs), {'json'})
        before = {p.relative_to(fixture.root).as_posix(): p.read_bytes()
                  for p in fixture.root.rglob('*') if p.is_file()}
        write_report_bundle(report, repo_root=fixture.root, destination=self.output)
        self.assertEqual(before, {p.relative_to(fixture.root).as_posix(): p.read_bytes()
                                 for p in fixture.root.rglob('*') if p.is_file()})
        for path in self.output.iterdir():
            self.assertNotIn(secret, path.read_text(encoding='utf8'))
