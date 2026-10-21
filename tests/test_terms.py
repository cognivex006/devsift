"""Offline terms engine tests using physical manifests, evidence and durable history."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devsift.terms import TermsAssessment, TermsError, assess_terms
from devsift.terms_memory import read_history, record_decision


NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class TermsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        self.home = self.base / 'home'
        self.catalog = self.base / 'catalog'
        self.catalog.mkdir()
        self.write('.devsift/third-party.json', {
            'schema_version': '1', 'components': [{'ecosystem': 'saas', 'name': 'provider/product',
                'version': 'business', 'kind': 'service', 'paths': ['deploy.json']}]})
        self.write('deploy.json', {'mode': 'forbidden-workload'})
        (self.catalog / 'terms.txt').write_text('Rule 1: forbidden-workload is prohibited.', encoding='utf-8')
        usage = (self.root / 'deploy.json').read_bytes()
        terms = (self.catalog / 'terms.txt').read_bytes()
        self.review = {
            'component': {'ecosystem': 'saas', 'name': 'provider/product', 'version': 'business', 'kind': 'service'},
            'rule_id': 'rule-1', 'applicability': 'applicable', 'conclusion': 'conflict',
            'seriousness': 'serious', 'rationale': 'Reviewed exact contrary use.',
            'recommendation': 'Remove the forbidden workload and verify replacement.',
            'evidence': [{'url': 'https://provider.example/terms', 'title': 'Terms', 'section': 'Rule 1',
                          'snapshot': 'terms.txt', 'sha256': digest(terms), 'excerpt': terms.decode()}],
            'usage_evidence': [{'path': 'deploy.json', 'sha256': digest(usage), 'excerpt': 'forbidden-workload'}]}
        self.data = {'schema_version': '1', 'policy_version': '1', 'reviewer': 'Operator reviewer',
            'reviewed_at': '2026-10-20T00:00:00Z', 'review_due': '2026-11-20T00:00:00Z',
            'reviews': [self.review]}

    def write(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value), encoding='utf-8')

    def assess(self, *, catalog=True, **kwargs):
        options = dict(as_of=NOW, history=read_history(self.root, home=self.home))
        if catalog:
            path = self.catalog / 'review.json'
            path.write_text(json.dumps(self.data), encoding='utf-8')
            options.update(catalog_path=path, catalog_digest=digest(path.read_bytes()))
        options.update(kwargs)
        return assess_terms(self.root, **options)

    def case(self, assessment):
        return next(case for case in assessment.to_dict()['cases'] if case['rule_id'] == 'rule-1')

    def decide(self, case, choice, supersedes=None):
        return record_decision(self.root, case_id=case['case_id'], fingerprint=case['fingerprint'],
            evidence_digest=case['evidence_digest'], choice=choice, owner='Fixture Owner',
            rationale='Explicit owner fixture decision', supersedes=supersedes, as_of=NOW, home=self.home)

    def test_confirmed_serious_block_is_sealed_and_read_only(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        assessed = self.assess()
        wire = assessed.to_dict()
        self.assertEqual((wire['status'], wire['enforced_count'], wire['complete']), ('blocked', 1, True))
        self.assertTrue(wire['decision_required'])
        self.assertEqual(self.case(assessed)['severity'], 'Critical')
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        with self.assertRaises(TermsError):
            TermsAssessment('fake', 'fake', '{}')
        wire['enforced_count'] = 0
        self.assertEqual(assessed.to_dict()['enforced_count'], 1)

    def test_unknown_inventory_does_not_erase_severe_floor(self):
        self.write('package.json', {'dependencies': {'unreviewed': '1.2.3'}})
        wire = self.assess().to_dict()
        self.assertEqual(wire['enforced_count'], 1)
        self.assertFalse(wire['complete'])
        self.assertEqual(wire['status'], 'blocked')
        unknown = next(c for c in wire['cases'] if c['component']['name'] == 'unreviewed')
        self.assertEqual(unknown['enforcement'], 'incomplete')

    def test_decline_persists_without_reprompt_and_still_blocks(self):
        initial = self.assess()
        event = self.decide(self.case(initial), 'decline')
        current = self.assess()
        case = self.case(current)
        self.assertEqual(case['decision']['event_id'], event['event_id'])
        self.assertFalse(case['decision_required'])
        self.assertEqual(current.to_dict()['enforced_count'], 1)
        self.assertNotEqual(initial.binding_digest, current.binding_digest)
        self.decide(case, 'reconsider', supersedes=event['event_id'])
        self.assertTrue(self.case(self.assess())['decision_required'])

    def test_resolution_claim_alone_does_not_unblock(self):
        initial = self.case(self.assess())
        self.decide(initial, 'resolved')
        current = self.assess()
        self.assertEqual(current.to_dict()['enforced_count'], 1)
        self.assertTrue(self.case(current)['decision_required'])

    def test_change_terms_usage_policy_or_version_reopens_review(self):
        baseline = self.assess()
        old = self.case(baseline)
        self.decide(old, 'decline')
        self.write('unrelated.txt', {'changed': True})
        unchanged = self.case(self.assess())
        self.assertEqual(old['fingerprint'], unchanged['fingerprint'])
        self.assertFalse(unchanged['decision_required'])
        self.data['policy_version'] = '2'
        policy = self.case(self.assess())
        self.assertNotEqual(old['fingerprint'], policy['fingerprint'])
        self.assertTrue(policy['decision_required'])
        self.assertIsNone(policy['decision'])
        self.assertEqual(len(policy['history']), 1)
        self.data['policy_version'] = '1'
        self.write('deploy.json', {'mode': 'forbidden-workload', 'changed': True})
        usage = self.case(self.assess())
        self.assertEqual(usage['status'], 'potential_conflict')
        self.assertTrue(usage['decision_required'])
        self.assertNotEqual(old['fingerprint'], usage['fingerprint'])
        self.review['component']['version'] = 'enterprise'
        self.write('.devsift/third-party.json', {'schema_version': '1', 'components': [
            {**self.review['component'], 'paths': ['deploy.json']}]})
        changed_version = self.assess()
        version = self.case(changed_version)
        self.assertNotEqual(old['case_id'], version['case_id'])
        self.assertNotEqual(old['fingerprint'], version['fingerprint'])
        self.assertTrue(changed_version.to_dict()['scope']['unmatched_decisions'])

    def test_simultaneous_versions_remember_independent_owner_decisions(self):
        first_component = dict(self.review['component'])
        second_component = dict(first_component, version='enterprise')
        self.write('.devsift/third-party.json', {'schema_version': '1', 'components': [
            {**component, 'paths': ['deploy.json']} for component in (first_component, second_component)]})
        self.data['reviews'].append(dict(self.review, component=second_component))
        initial = self.assess().to_dict()
        cases = initial['cases']
        self.assertEqual(len({case['case_id'] for case in cases}), 2)
        for case in cases:
            self.decide(case, 'decline')
        remembered = self.assess().to_dict()
        self.assertEqual(remembered['enforced_count'], 2)
        self.assertFalse(remembered['decision_required'])
        self.assertTrue(all(case['decision']['choice'] == 'decline' and len(case['history']) == 1
                            for case in remembered['cases']))
        self.assertEqual(remembered['scope']['unmatched_decisions'], [])
        self.write('.devsift/third-party.json', {'schema_version': '1', 'components': [
            {**dict(first_component, version='new-plan'), 'paths': ['deploy.json']},
            {**second_component, 'paths': ['deploy.json']}]})
        self.review['component'] = dict(first_component, version='new-plan')
        changed = self.assess().to_dict()
        new_case = next(case for case in changed['cases'] if case['component']['version'] == 'new-plan')
        self.assertTrue(new_case['decision_required'])
        self.assertIsNone(new_case['decision'])
        self.assertEqual(len(changed['scope']['unmatched_decisions']), 1)
        self.assertEqual(changed['scope']['unmatched_decisions'][0]['case_id'],
                         next(case['case_id'] for case in cases if case['component']['version'] == 'business'))

    def test_freshness_and_bad_evidence_never_confirm(self):
        for field, value in [('review_due', '2026-10-21T00:00:00Z'),
                             ('reviewed_at', '2026-10-22T00:00:00Z')]:
            with self.subTest(field=field):
                old = self.data[field]
                self.data[field] = value
                wire = self.assess().to_dict()
                self.assertFalse(wire['complete'])
                self.assertEqual(wire['enforced_count'], 0)
                self.assertEqual(self.case(self.assess())['status'], 'stale')
                self.data[field] = old
        for entry, key, value in [(self.review['evidence'][0], 'sha256', '0' * 64),
                                  (self.review['usage_evidence'][0], 'excerpt', 'not present')]:
            old = entry[key]
            entry[key] = value
            wire = self.assess().to_dict()
            self.assertFalse(wire['complete'])
            self.assertEqual(wire['enforced_count'], 0)
            entry[key] = old
        self.review['usage_evidence'] = []
        self.assertEqual(self.case(self.assess())['status'], 'potential_conflict')

    def test_expired_matching_decision_is_history_only(self):
        first = self.case(self.assess())
        self.decide(first, 'decline')
        expired = self.case(self.assess(as_of=datetime(2026, 11, 21, tzinfo=timezone.utc)))
        self.assertEqual(first['fingerprint'], expired['fingerprint'])
        self.assertEqual(expired['status'], 'stale')
        self.assertIsNone(expired['decision'])
        self.assertTrue(expired['history'])
        self.assertTrue(expired['decision_required'])

    def test_compliant_not_applicable_and_ordinary_conflict(self):
        self.review['conclusion'] = 'compliant'
        self.assertEqual(self.case(self.assess())['status'], 'reviewed_compliant')
        self.review['applicability'] = 'not_applicable'
        self.review['usage_evidence'] = []
        self.assertEqual(self.case(self.assess())['status'], 'reviewed_not_applicable')
        self.review['applicability'] = 'unknown'
        self.assertFalse(self.assess().to_dict()['complete'])

    def test_reject_unsafe_catalog_schema_url_and_physical_paths(self):
        for key, value in [('snapshot', '../terms.txt'), ('snapshot', '.git/config'),
                           ('snapshot', '.GIT /config'), ('snapshot', '.git./config'),
                           ('snapshot', 'NUL.txt'), ('snapshot', 'safe.txt:secret'),
                           ('url', 'http://provider.example/terms'),
                           ('url', 'https://u:p@provider.example/terms'),
                           ('url', 'https://provider.example/terms?token=secret')]:
            with self.subTest(key=key, value=value):
                entry = self.review['evidence'][0]
                old = entry[key]
                entry[key] = value
                wire = self.assess().to_dict()
                self.assertIn('TERMS_CATALOG_INVALID', wire['errors'])
                self.assertEqual(wire['enforced_count'], 0)
                entry[key] = old
        self.data['extra'] = 'unexpected'
        self.assertIn('TERMS_CATALOG_INVALID', self.assess().to_dict()['errors'])
        del self.data['extra']
        self.data['reviews'].append(dict(self.review))
        self.assertIn('TERMS_CATALOG_INVALID', self.assess().to_dict()['errors'])

    def test_reordered_component_keys_cannot_bypass_conflicting_duplicate_rejection(self):
        reversed_component = dict(reversed(list(self.review['component'].items())))
        self.assertNotEqual(list(reversed_component), list(self.review['component']))
        duplicate = dict(self.review, component=reversed_component, conclusion='compliant')
        self.data['reviews'].append(duplicate)
        wire = self.assess().to_dict()
        self.assertIn('TERMS_CATALOG_INVALID', wire['errors'])
        self.assertFalse(wire['complete'])
        self.assertEqual(wire['enforced_count'], 0)
        self.assertEqual(len({case['case_id'] for case in wire['cases']}), len(wire['cases']))
        self.assertTrue(all(case['status'] == 'unknown' for case in wire['cases']))

    def test_redaction_uses_full_evidence_context(self):
        secret = 'ghp_' + 'a' * 32
        usage = json.dumps({'mode': 'forbidden-workload', 'token': secret}).encode()
        (self.root / 'deploy.json').write_bytes(usage)
        self.review['usage_evidence'][0].update(sha256=digest(usage), excerpt=usage.decode())
        self.review['rationale'] = 'token=' + secret
        wire = self.assess().to_dict()
        self.assertNotIn(secret, json.dumps(wire))
        self.assertIn('[REDACTED]', json.dumps(wire))

    def test_partial_secret_excerpt_cannot_restore_masked_source(self):
        secret = 'fixturePlainUnknownCredential12345'
        usage = json.dumps({'api_key': secret, 'mode': 'forbidden-workload'}).encode()
        (self.root / 'deploy.json').write_bytes(usage)
        fragment = secret[5:20]
        self.review['usage_evidence'][0].update(sha256=digest(usage), excerpt=fragment)
        wire = self.assess().to_dict()
        self.assertNotIn(fragment, json.dumps(wire))
        self.assertEqual(self.case(self.assess())['usage_evidence'][0]['excerpt'], '[REDACTED]')

    def test_changed_terms_bytes_reopen_but_unrelated_reviews_do_not(self):
        first = self.case(self.assess())
        self.decide(first, 'decline')
        unrelated = dict(self.review, component=dict(self.review['component'], name='unused'))
        self.data['reviews'].append(unrelated)
        self.assertEqual(first['fingerprint'], self.case(self.assess())['fingerprint'])
        raw = b'Rule 1: forbidden-workload is prohibited. Updated clause.'
        (self.catalog / 'terms.txt').write_bytes(raw)
        self.review['evidence'][0]['sha256'] = digest(raw)
        changed = self.case(self.assess())
        self.assertNotEqual(first['fingerprint'], changed['fingerprint'])
        self.assertTrue(changed['decision_required'])
        self.assertEqual(changed['status'], 'confirmed_serious_conflict')

    def test_missing_declared_usage_preserves_case_and_stale_history(self):
        first = self.case(self.assess())
        self.decide(first, 'decline')
        (self.root / 'deploy.json').unlink()
        current = self.assess()
        case = self.case(current)
        self.assertEqual(case['status'], 'potential_conflict')
        self.assertTrue(case['history'])
        self.assertTrue(case['decision_required'])
        self.assertFalse(current.to_dict()['complete'])

    def test_missing_catalog_preserves_unmatched_owner_history_in_scope(self):
        first = self.case(self.assess())
        event = self.decide(first, 'decline')
        wire = self.assess(catalog=False).to_dict()
        self.assertFalse(wire['complete'])
        self.assertEqual(wire['scope']['unmatched_decisions'][0]['event_id'], event['event_id'])

    def test_nested_transitive_manifests_and_explicit_services(self):
        self.write('sub/package.json', {'dependencies': {'alpha': '1.0.0'}, 'devDependencies': {'dev': '2'}})
        self.write('sub/package-lock.json', {'lockfileVersion': 3, 'packages': {
            '': {'dependencies': {'alpha': '1.0.0'}},
            'node_modules/alpha': {'version': '1.0.0'},
            'node_modules/alpha/node_modules/transitive': {'version': '3.0.0'}}})
        (self.root / 'pyproject.toml').write_text('[build-system]\nrequires=["setuptools==83.0.0"]\n'
            '[project]\ndependencies=["Foo_Bar==1.2"]\n', encoding='utf-8')
        (self.root / 'go.mod').write_text('module fixture\nrequire (\nexample.test/a v1.0.0\n'
            'example.test/b v2.0.0 // indirect\n)\n', encoding='utf-8')
        (self.root / 'app.csproj').write_text('<Project><ItemGroup><PackageReference Include="Example" '
            'Version="[1.2.0]"/><Reference Include="SDK.Assembly"/></ItemGroup></Project>', encoding='utf-8')
        self.write('packages.lock.json', {'dependencies': {'net9.0': {
            'Example': {'type': 'Direct', 'resolved': '1.2.0'},
            'Indirect': {'type': 'Transitive', 'resolved': '2.0.0'}}}})
        wire = self.assess(catalog=False).to_dict()
        items = {(c['name'], c['version']): c for c in wire['inventory']}
        self.assertEqual(items['transitive', '3.0.0']['relationship'], 'transitive')
        self.assertEqual(items['Indirect', '2.0.0']['relationship'], 'transitive')
        self.assertEqual(items['example.test/b', 'v2.0.0']['relationship'], 'transitive')
        self.assertEqual(items['setuptools', '83.0.0']['kind'], 'build')
        self.assertIn(('foo-bar', '1.2'), items)
        self.assertIn(('provider/product', 'business'), items)
        self.assertIn('TERMS_ASSEMBLY_REQUIRES_DECLARATION', wire['errors'])
        self.assertFalse(wire['complete'])

    def test_manifest_limit_and_malformed_manifest_are_visible(self):
        self.write('package.json', {'dependencies': {'bad': 42}})
        wire = self.assess().to_dict()
        self.assertIn('TERMS_MANIFEST_INVALID', wire['errors'])
        self.assertEqual(wire['enforced_count'], 1)
        self.assertFalse(wire['complete'])

    def test_manifest_limit_returns_explicit_incomplete(self):
        for index in range(257):
            self.write(f'projects/{index:03}/package.json', {})
        wire = self.assess().to_dict()
        self.assertIn('TERMS_DISCOVERY_LIMIT', wire['errors'])
        self.assertFalse(wire['complete'])

    def test_manifest_range_reconciles_with_direct_lock_only(self):
        self.write('package.json', {'dependencies': {'alpha': '^1.0.0'}})
        self.write('package-lock.json', {'packages': {'': {'dependencies': {'alpha': '^1.0.0'}},
            'node_modules/alpha': {'version': '1.1.0'},
            'node_modules/alpha/node_modules/alpha': {'version': '1.2.0'}}})
        wire = self.assess(catalog=False).to_dict()
        # Nested copies must not be mistaken for the root direct dependency.
        entries = [item for item in wire['inventory'] if item['name'] == 'alpha']
        self.assertEqual({item['version'] for item in entries}, {'1.1.0', '1.2.0'})
        self.assertEqual(next(item for item in entries if item['version'] == '1.2.0')['relationship'], 'transitive')

    def test_direct_lock_provenance_does_not_cross_workspace_transitive_copy(self):
        self.write('package-lock.json', {'packages': {'': {'dependencies': {'alpha': '1.1.0'}},
            'node_modules/alpha': {'version': '1.1.0'}}})
        self.write('sub/package.json', {'dependencies': {'alpha': '^1.0.0'}})
        self.write('sub/package-lock.json', {'packages': {'': {'dependencies': {'beta': '1.0.0'}},
            'node_modules/beta': {'version': '1.0.0'},
            'node_modules/beta/node_modules/alpha': {'version': '1.1.0'}}})
        wire = self.assess(catalog=False).to_dict()
        alpha = [item for item in wire['inventory'] if item['name'] == 'alpha']
        self.assertEqual({item['version'] for item in alpha}, {'1.1.0', '^1.0.0'})
        declared = next(item for item in alpha if item['version'] == '^1.0.0')
        self.assertEqual(declared['paths'], ['sub/package.json'])

    def test_output_overflow_keeps_sealed_assessment_and_serious_floor(self):
        component = dict(self.review['component'], name='provider/' + 'n' * 480, version='v' * 490)
        components = [{**component, 'name': component['name'] + str(index), 'paths': ['deploy.json']}
                      for index in range(1000)]
        self.write('.devsift/third-party.json', {'schema_version': '1', 'components': components})
        self.data['reviews'] = [dict(self.review, component={key: components[0][key]
            for key in ('ecosystem', 'name', 'version', 'kind')}, rule_id=f'rule-{index}') for index in range(1000)]
        assessment = self.assess()
        self.assertIs(type(assessment), TermsAssessment)
        wire = assessment.to_dict()
        self.assertIn('TERMS_OUTPUT_LIMIT', wire['errors'])
        self.assertFalse(wire['complete'])
        self.assertEqual(wire['enforced_count'], 1000)
        self.assertEqual(sum(case['enforcement'] == 'block' for case in wire['cases']), 1000)
        self.assertEqual(wire['status'], 'blocked')
        self.assertEqual(len(wire['cases']), 1999)

    def test_default_history_is_always_read_and_forged_history_fails_closed(self):
        from devsift import terms_memory
        original = terms_memory.read_history
        with patch.object(terms_memory, 'read_history', side_effect=lambda root: original(root, home=self.home)) as reader:
            assessment = assess_terms(self.root, as_of=NOW)
            reader.assert_called_once()
            self.assertEqual(assessment.to_dict()['history_revision'], original(self.root, home=self.home).revision)
        self.assertIn('TERMS_HISTORY_UNAVAILABLE', self.assess(history={}).to_dict()['errors'])

    def test_bindings_stable_until_expiry(self):
        first = self.assess()
        later = self.assess(as_of=datetime(2026, 10, 22, tzinfo=timezone.utc))
        self.assertEqual(first.binding_digest, later.binding_digest)
        self.data['review_due'] = '2026-10-22T00:00:00Z'
        expired = self.assess(as_of=datetime(2026, 10, 23, tzinfo=timezone.utc))
        self.assertNotEqual(first.binding_digest, expired.binding_digest)

    def test_symlinked_usage_not_trusted(self):
        outside = self.base / 'outside.json'
        outside.write_bytes((self.root / 'deploy.json').read_bytes())
        (self.root / 'deploy.json').unlink()
        try:
            os.symlink(outside, self.root / 'deploy.json')
        except OSError:
            self.skipTest('Host does not permit symlink creation')
        wire = self.assess().to_dict()
        self.assertEqual(wire['enforced_count'], 0)
        self.assertFalse(wire['complete'])


if __name__ == '__main__':
    unittest.main()
