from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from devsift.observability import NoiseMeasurement, RuntimeEvent, analyze_noise


class NoiseTests(unittest.TestCase):
    def event(self, identity, **overrides):
        return RuntimeEvent(**(dict(event_id=identity, pair_id='specific-request-hop', side='upstream',
                                     boundary_id='actual-client-boundary', event_kind='routine_success',
                                     emission_role='completion') | overrides))

    def measurement(self, **overrides):
        return NoiseMeasurement(**(dict(boundary_id='actual-client-boundary', coverage_complete=True,
                                        equivalent_emissions=True) | overrides))

    def test_actual_equivalent_completions_produce_bounded_advisory_review(self):
        observation, = analyze_noise((self.event('first'), self.event('second')), (self.measurement(),))
        self.assertEqual(observation.status, 'duplicate_observed')
        self.assertEqual(observation.observed_event_count, 2)
        self.assertIsNotNone(observation.recommendation)
        self.assertEqual(observation.enforcement, 'advisory')
        self.assertEqual(observation.lifecycle_class, 'UNKNOWN')
        self.assertFalse(observation.automatic_fix)
        self.assertEqual(observation.to_dict()['volume_status'], 'unknown')

    def test_distinct_requests_sides_roles_and_same_free_text_are_not_duplicates(self):
        first = self.event('first', message='Identical free text')
        for other in (self.event('second', pair_id='different-request-hop', message='Identical free text'),
                      self.event('second', side='downstream', message='Identical free text'),
                      self.event('second', emission_role='start', message='Identical free text')):
            with self.subTest(other=other):
                observations = analyze_noise((first, other), (self.measurement(),))
                self.assertTrue(all(item.recommendation is None for item in observations))
                self.assertTrue(all(item.status != 'duplicate_observed' for item in observations))

    def test_missing_coverage_semantic_equivalence_and_boundaries_stay_unresolved(self):
        events = (self.event('first'), self.event('second'))
        for measurements in ((), (self.measurement(coverage_complete=False),),
                             (self.measurement(equivalent_emissions=False),)):
            self.assertTrue(all(item.recommendation is None for item in analyze_noise(events, measurements)))
        unknown = (self.event('first', boundary_id=None), self.event('second', boundary_id=None))
        self.assertTrue(all(item.recommendation is None for item in analyze_noise(unknown, (self.measurement(),))))

    def test_audit_security_auth_rejection_and_unknown_classification_are_preserved(self):
        for kind in ('audit', 'security', 'auth_rejection', 'unknown'):
            with self.subTest(kind=kind):
                events = (self.event('first'), self.event('second'),
                          self.event('protected', event_kind=kind, emission_role='start', message='Expected HTTP 401'))
                observations = analyze_noise(events, (self.measurement(),))
                self.assertTrue(all(item.recommendation is None for item in observations))
                self.assertTrue(all(item.enforcement == 'advisory' for item in observations))

    def test_measured_window_is_only_actual_sample_count_and_consumer_claim_stays_unknown(self):
        measurement = self.measurement(window_seconds=2.5, consumers_reviewed=True)
        observation, = analyze_noise((self.event('first'), self.event('second')), (measurement,))
        wire = observation.to_dict()
        self.assertEqual(wire['measurement']['observed_event_count'], 2)
        self.assertEqual(wire['measurement']['window_seconds'], 2.5)
        self.assertEqual(wire['volume_status'], 'measured_sample')
        self.assertEqual(wire['consumer_status'], 'unknown')
        self.assertEqual(wire['risk_if_changed']['level'], 'unknown')
        self.assertTrue(wire['consumer_review_declared'])
        self.assertNotIn('production_rate', json.dumps(wire))

    def test_repeated_event_identity_does_not_become_measured_duplicate(self):
        observations = analyze_noise((self.event('same'), self.event('same')), (self.measurement(),))
        self.assertTrue(all(item.recommendation is None for item in observations))

    def test_privacy_fresh_json_frozen_results_and_deterministic_order(self):
        private = 'alice@example.invalid token=private-fixture-secret'
        events = (self.event(private, boundary_id=private, pair_id=private, message=private),
                  self.event('second', boundary_id=private, pair_id=private, correlation_id=private))
        measurement = self.measurement(boundary_id=private)
        first = analyze_noise(events, (measurement,))
        self.assertEqual(first, analyze_noise(tuple(reversed(events)), (measurement,)))
        self.assertNotIn(private, json.dumps(first[0].to_dict()) + repr(events) + repr(measurement))
        with self.assertRaises(FrozenInstanceError):
            first[0].observed_event_count = 999
        wire = first[0].to_dict()
        wire['measurement']['observed_event_count'] = 999
        wire['runtime_evidence'].clear()
        self.assertEqual(first[0].to_dict()['measurement']['observed_event_count'], 2)
        self.assertTrue(first[0].to_dict()['runtime_evidence'])
        self.assertEqual(first[0].source.status, 'SOURCE_UNRESOLVED')

    def test_invalid_measurements_and_bounds_fail_safely(self):
        for overrides in ({'coverage_complete': 1}, {'equivalent_emissions': 'yes'},
                          {'consumers_reviewed': None}, {'window_seconds': True},
                          {'window_seconds': 0}, {'window_seconds': float('nan')},
                          {'window_seconds': float('inf')}):
            with self.assertRaises(ValueError):
                self.measurement(**overrides)
        with self.assertRaises(ValueError):
            self.event('first', event_kind='arbitrary')
        with self.assertRaises(ValueError):
            analyze_noise((self.event('first'),) * 1001, ())
        with self.assertRaises(ValueError):
            analyze_noise((), (self.measurement(), self.measurement()))

    def test_analysis_does_not_write_source_or_logs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'observed.log').write_bytes(b'unchanged actual fixture\n')
            (root / 'empty').mkdir()
            before = {p.name: None if p.is_dir() else p.read_bytes() for p in root.iterdir()}
            analyze_noise((self.event('first'), self.event('second')), (self.measurement(),))
            self.assertEqual(before, {p.name: None if p.is_dir() else p.read_bytes() for p in root.iterdir()})


if __name__ == '__main__':
    unittest.main()
