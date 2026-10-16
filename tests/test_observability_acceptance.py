"""Independent structured collector fixtures; no production telemetry is claimed."""
from contextlib import ExitStack
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from devsift.observability import (CorrelationCoverage, NoiseMeasurement, RuntimeEvent,
                                    analyze_correlation, analyze_noise)
from devsift.redaction import Redactor

FIXTURES = Path(__file__).resolve().parent / 'fixtures/observability'
COMMON_FIELDS = {'context_id', 'category', 'status', 'reason', 'human_explanation',
                 'coverage_complete', 'runtime_evidence', 'source', 'enforcement',
                 'lifecycle_class', 'automatic_fix', 'recommendation', 'approval_status',
                 'volume_status', 'consumer_status', 'impact_if_unchanged', 'risk_if_changed',
                 'review_prompt', 'implement_prompt'}
NOISE_FIELDS = COMMON_FIELDS | {'equivalence_declared', 'measurement', 'consumer_review_declared'}


def cases(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def analyze(case, *, noise=False, redactor=None):
    events = tuple(RuntimeEvent(**item) for item in case['events'])
    if noise:
        return analyze_noise(events, tuple(NoiseMeasurement(**item) for item in case['measurements']), redactor=redactor)
    return analyze_correlation(events, tuple(CorrelationCoverage(**item) for item in case['coverage']), redactor=redactor)


class ObservabilityAcceptance(unittest.TestCase):
    def assert_context_contract(self, observation, *, noise=False):
        wire = observation.to_dict()
        self.assertEqual(set(wire), NOISE_FIELDS if noise else COMMON_FIELDS)
        self.assertEqual(wire['enforcement'], 'advisory')
        self.assertEqual(wire['lifecycle_class'], 'UNKNOWN')
        self.assertIs(wire['automatic_fix'], False)
        self.assertEqual(wire['approval_status'], 'not_requested')
        self.assertEqual(wire['source']['status'], 'SOURCE_UNRESOLVED')
        self.assertIsNone(wire['source']['location'])
        self.assertIsNone(wire['source']['before'])
        self.assertTrue(wire['source']['lookup_plan'])
        self.assertEqual(wire['consumer_status'], 'unknown')
        self.assertEqual(wire['risk_if_changed']['level'], 'unknown')
        self.assertEqual(wire['impact_if_unchanged']['level'], 'unknown')
        self.assertTrue(wire['runtime_evidence'])
        self.assertTrue(wire['implement_prompt'].startswith('Only after'))
        self.assertNotIn('rule_id', wire)
        self.assertNotIn('Critical', json.dumps(wire))
        self.assertNotIn('upstream_duration', json.dumps(wire))
        return wire

    def test_external_otel_cookie_cors_304_and_proven_missing_link_expectations(self):
        for case in cases('correlation.json'):
            with self.subTest(case=case['case']):
                observed = analyze(case)
                self.assertEqual([item.status for item in observed], case['expected']['statuses'])
                self.assertEqual([item.reason for item in observed], case['expected']['reasons'])
                self.assertEqual(any(item.recommendation is not None for item in observed),
                                 case['expected']['recommendation'])
                for item in observed:
                    wire = self.assert_context_contract(item)
                    self.assertEqual(wire['volume_status'], 'unknown')

    def test_external_filter_auth_security_and_sample_volume_expectations(self):
        for case in cases('noise.json'):
            with self.subTest(case=case['case']):
                observed = analyze(case, noise=True)
                self.assertEqual([item.status for item in observed], case['expected']['statuses'])
                self.assertEqual([item.reason for item in observed], case['expected']['reasons'])
                self.assertEqual([item.observed_event_count for item in observed], case['expected']['counts'])
                self.assertEqual(any(item.recommendation is not None for item in observed),
                                 case['expected']['recommendation'])
                for item in observed:
                    wire = self.assert_context_contract(item, noise=True)
                    self.assertEqual(wire['volume_status'], case['expected']['volume'])
                    self.assertEqual(set(wire['measurement']), {'observed_event_count', 'window_seconds', 'scope'})
                    self.assertEqual(wire['measurement']['scope'], 'supplied_operation_sample')
                    self.assertNotIn('production_rate', wire['measurement'])

    def test_handled_401_retains_cross_side_audit_and_security_protection(self):
        case = next(item for item in cases('noise.json') if item['case'] == 'handled_401_security_audit_retained_across_sides')
        self.assertEqual(case['http']['status_code'], 401)
        self.assertTrue(case['http']['handled_authentication_rejection'])
        self.assertEqual({item['event_kind'] for item in case['events']},
                         {'routine_success', 'auth_rejection', 'security', 'audit'})
        observed = analyze(case, noise=True)
        self.assertEqual(sum(item.observed_event_count for item in observed), 5)
        self.assertTrue(all(item.status == 'preserve_protected' for item in observed))
        self.assertTrue(all(item.recommendation is None for item in observed))
        self.assertTrue(all(not item.automatic_fix for item in observed))

    def test_raw_identifiers_messages_pii_and_secrets_never_become_report_evidence(self):
        for name, noise in (('correlation.json', False), ('noise.json', True)):
            for case in cases(name):
                with self.subTest(case=case['case']):
                    wire = json.dumps([item.to_dict() for item in analyze(case, noise=noise)])
                    for event in case['events']:
                        for key in ('event_id', 'pair_id', 'trace_id', 'span_id', 'parent_span_id', 'correlation_id', 'boundary_id'):
                            if event.get(key):
                                self.assertNotIn(event[key], wire)
                    self.assertNotIn('alice@example.invalid', wire)
                    self.assertNotIn('private-fixture-secret', wire)
                    self.assertNotIn('ActionLoggingFilter', wire)
                    self.assertNotIn('ResponseMiddleware', wire)

    def test_custom_redactor_reserved_words_do_not_mutate_schema_keys_or_status_enums(self):
        redactor = Redactor(('context_id', 'category', 'UNKNOWN', 'advisory', 'measurement',
                             'window_seconds', 'coverage_complete', 'PROTECTED_EVENT', 'TRACE_MISMATCH'))
        for name, noise in (('correlation.json', False), ('noise.json', True)):
            for case in cases(name):
                with self.subTest(case=case['case']):
                    masked = analyze(case, noise=noise, redactor=redactor)
                    self.assertEqual([item.reason for item in masked], case['expected']['reasons'])
                    self.assertEqual([item.status for item in masked], case['expected']['statuses'])
                    for observation in masked:
                        self.assert_context_contract(observation, noise=noise)

    def test_fixture_analysis_is_read_only_and_requires_no_native_network_or_database(self):
        correlation, noise = cases('correlation.json'), cases('noise.json')
        before = {p.name: p.read_bytes() for p in FIXTURES.iterdir() if p.is_file()}
        with ExitStack() as stack:
            for operation in ('builtins.open', 'subprocess.Popen', 'socket.create_connection', 'sqlite3.connect'):
                stack.enter_context(patch(operation, side_effect=AssertionError('Unexpected external operation')))
            for case in correlation:
                analyze(case)
            for case in noise:
                analyze(case, noise=True)
        self.assertEqual(before, {p.name: p.read_bytes() for p in FIXTURES.iterdir() if p.is_file()})


if __name__ == '__main__':
    unittest.main()
