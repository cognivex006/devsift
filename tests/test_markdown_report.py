import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devsift.adapters import AdapterCapability
from devsift.evidence import Region, SourceEvidence, verify_source
from devsift.markdown_report import MarkdownError, render_markdown
from devsift.output import result
from devsift.redaction import Redactor
from devsift.report_model import assemble_report
from devsift.scanner import AdapterOutcome, ScanFinding, scan

GOLDEN = Path(__file__).resolve().parent / 'fixtures/reports/markdown-case-contract.json'


class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = 'client.ts'
        self.source = 'fetch("https://api.example.invalid");\r\nconsole.log("ready");\r\n'
        self.commit_source()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True).stdout.decode().strip()

    def commit_source(self):
        (self.root / self.path).write_bytes(self.source.encode('utf-8'))
        if not (self.root / '.git').exists():
            self.git('init', '-q')
            self.git('config', 'user.name', 'Fixture')
            self.git('config', 'user.email', 'fixture@example.invalid')
            self.git('config', 'core.autocrlf', 'false')
        self.git('add', self.path)
        self.git('commit', '-qm', 'fixture')
        self.sha = self.git('rev-parse', 'HEAD')

    def report(self, rules=('HC001',), *, unresolved=False, lifecycle='UNKNOWN', redactor=None, region=None, repository='local'):
        region = region or Region(1, 1, 2, len(self.source.split('\n')[1].removesuffix('\r')) + 1)
        proof = SourceEvidence() if unresolved else verify_source(self.root, repository, self.sha, self.path, region)
        findings = [dict(case_id=f'CASE-{number}', rule_id=rule, message='untrusted text', path=self.path,
                         source=proof.to_dict(), severity='Warning', lifecycle_class=lifecycle,
                         enforcement='advisory', security_escalation=False) for number, rule in enumerate(rules, 1)]
        return assemble_report(result('scan', complete=True, findings=findings), repo_root=self.root,
                               trusted_lifecycles=True, redactor=redactor,
                               repository_urls=((repository, 'https://github.com/owner/repo'),))

    def test_independent_full_case_golden_fields_and_inline_prompts_for_every_case(self):
        report = self.report(('HC001', 'LOG001'))
        markdown = render_markdown(report)
        golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
        for index, case in enumerate(report.cases, 1):
            section = markdown.split(f'<a id="case-{index:04}"></a>')[1]
            if index < len(report.cases):
                section = section.split(f'<a id="case-{index + 1:04}"></a>')[0]
            for heading in golden['headings']:
                self.assertIn(heading, section)
            for text in golden['required_text']:
                for sentence in text.split('. '):
                    self.assertIn(sentence.rstrip('.'), section)
            wire = report.find_case(case.case_id).to_dict()
            self.assertIn(wire['review_prompt'], section)
            self.assertIn(wire['implement_prompt'], section)
            self.assertIn(golden['no_verified_proposal'], section)
            self.assertIn(f'](#case-{index:04})', markdown)
        self.assertIn('1 | fetch(', markdown)
        self.assertIn('\r\n2 | console.log(', markdown)
        self.assertIn(self.sha, markdown)

    def test_whole_secret_mask_and_overlapping_case_never_reveal_raw_source(self):
        private = 'fixtureOddCredentialValue'
        self.source = 'console.log("' + private + '");\n'
        self.commit_source()
        region = Region(1, 1, 1, len(self.source.rstrip('\n')) + 1)
        # Existing authoritative security masks must survive the overlapping rule.
        proof = verify_source(self.root, 'local', self.sha, self.path, region, sensitive=True)
        class FixtureAdapter:
            capability = AdapterCapability('fixture-source-proof', '1', ('typescript',), True)
            def analyze(self, target):
                return AdapterOutcome(True, tuple(ScanFinding(f'SECRET-{index}', rule, proof,
                                        lifecycle_class='LEGACY_UNCHANGED')
                                        for index, rule in enumerate(('HC002', 'LOG001'), 1)))
        record = scan(self.root, (self.path,), adapters=(FixtureAdapter(),))
        self.assertNotIn(private, json.dumps(record))
        report = assemble_report(record, repo_root=self.root, trusted_lifecycles=True)
        markdown = render_markdown(report)
        self.assertNotIn(private, markdown)
        self.assertEqual(markdown.count('[REDACTED]'), 2)
        self.assertIn('security_review', markdown)
        self.assertIn('Security escalation: true', markdown)

    def test_invisible_controls_are_displayed_without_mutating_proven_source(self):
        self.path = 'unicode\u202e[view].ts'
        self.source = 'const x = "😀\u202e\u2028\x1b[31m";\n'
        self.commit_source()
        report = self.report(region=Region(1, 1, 1, len(self.source.rstrip('\n')) + 1))
        markdown = render_markdown(report)
        self.assertNotIn('\u202e', markdown)
        self.assertNotIn('\u2028', markdown)
        self.assertNotIn('\x1b', markdown)
        self.assertIn(r'\u202e', markdown)
        self.assertIn(r'\u2028', markdown)
        self.assertIn(r'\u001b', markdown)
        self.assertIn('\u202e', report.cases[0].source.before)

    def test_untrusted_repository_prose_cannot_create_html_markdown_or_links(self):
        label = 'local **bold** [click](https://evil.invalid) <img src=x onerror=alert(1)>'
        markdown = render_markdown(self.report(repository=label))
        self.assertNotIn('<img', markdown)
        self.assertIn('&lt;img', markdown)
        self.assertNotIn('**bold**', markdown)
        self.assertNotIn('[click](https://evil.invalid)', markdown)
        self.assertNotIn('https://evil.invalid', markdown)
        self.assertIn('https://github.com/owner/repo/blob/', markdown)

    def test_whole_multiline_mask_and_exclusive_empty_regions_do_not_invent_lines(self):
        full = render_markdown(self.report(('HC002',)))
        self.assertIn('1-2 | [REDACTED]', full)
        exclusive = render_markdown(self.report(('HC002',), region=Region(1, 1, 2, 1)))
        self.assertIn('1 | [REDACTED]', exclusive)
        self.assertNotIn('1-2 | [REDACTED]', exclusive)
        empty = render_markdown(self.report(region=Region(1, 1, 1, 1)))
        self.assertIn('Verified zero-width region', empty)
        before_section = empty.split('### BEFORE', 1)[1].split('### AFTER', 1)[0]
        self.assertNotIn('1 | ', before_section)

    def test_empty_incomplete_report_has_no_invented_cases_or_source(self):
        report = assemble_report(result('scan', complete=False,
                                       errors=[{'code': 'ADAPTER_FAILED', 'message': 'private error'}]),
                                 repo_root=self.root)
        markdown = render_markdown(report)
        self.assertIn('Status: incomplete', markdown)
        self.assertIn('No cases supplied.', markdown)
        self.assertNotIn('private error', markdown)
        self.assertNotIn('## Case ', markdown)

    def test_dynamic_fences_html_markdown_path_and_unicode_are_safe(self):
        self.path = 'view[click](evil).ts'
        self.source = 'const text = "😀";\r\n```\r\n<script>alert("x")</script>\r\n`````\r\n'
        self.commit_source()
        report = self.report(region=Region(1, 1, 4, 6))
        markdown = render_markdown(report)
        self.assertIn('``````text', markdown)
        self.assertIn('3 | <script>alert("x")</script>', markdown)
        self.assertNotIn('Path: view[click](evil).ts', markdown)
        self.assertIn(r'view\[click\]\(evil\)\.ts', markdown)
        self.assertIn('😀', markdown)
        self.assertIn('/view%5Bclick%5D%28evil%29.ts#L1-L4', markdown)

    def test_unresolved_source_never_has_fake_path_line_or_navigation(self):
        markdown = render_markdown(self.report(unresolved=True))
        self.assertIn('SOURCE_UNRESOLVED', markdown)
        self.assertIn('Lookup plan:', markdown)
        self.assertNotIn('github.com', markdown)
        self.assertNotIn('client.ts', markdown)
        self.assertNotIn('L0', markdown)
        self.assertNotIn('file://', markdown)

    def test_reserved_word_redactor_does_not_change_model_enums_or_renderer_structure(self):
        report = self.report(redactor=Redactor(('unknown', 'source', 'cases', 'pending')))
        markdown = render_markdown(report)
        self.assertIn('Confidence: unknown', markdown)
        self.assertIn('Approval: pending', markdown)
        self.assertIn('### Source evidence', markdown)

    def test_read_only_deterministic_strict_type_and_bounded_output(self):
        report = self.report()
        before = {str(p.relative_to(self.root)): None if p.is_dir() else p.read_bytes() for p in self.root.rglob('*')}
        first = render_markdown(report)
        self.assertEqual(first, render_markdown(report))
        self.assertEqual(before, {str(p.relative_to(self.root)): None if p.is_dir() else p.read_bytes() for p in self.root.rglob('*')})
        for bad in ({}, report.to_dict(), None):
            with self.assertRaises(MarkdownError):
                render_markdown(bad)
        with patch('devsift.markdown_report.MAX_OUTPUT_BYTES', 100):
            with self.assertRaises(MarkdownError):
                render_markdown(report)


if __name__ == '__main__':
    unittest.main()
