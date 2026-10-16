from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from devsift.observability import CorrelationCoverage, RuntimeEvent, analyze_correlation


class CorrelationTests(unittest.TestCase):
    def upstream(self, **overrides):
        values = dict(event_id='outbound', pair_id='actual-hop', side='upstream',
                      trace_id='a' * 32, span_id='1' * 16, context_observed=True)
        return RuntimeEvent(**(values | overrides))

    def downstream(self, **overrides):
        values = dict(event_id='inbound', pair_id='actual-hop', side='downstream',
                      trace_id='a' * 32, span_id='2' * 16, parent_span_id='1' * 16,
                      context_observed=True)
        return RuntimeEvent(**(values | overrides))

    def coverage(self, **overrides):
        return CorrelationCoverage(**(dict(pair_id='actual-hop', upstream_complete=True,
                                          downstream_complete=True, propagation_expected=True) | overrides))

    def test_actual_parent_edge_is_continuous_without_custom_cookie_or_duration(self):
        events = (self.downstream(correlation_id=None), self.upstream(correlation_id='optional-custom-id'))
        observation, = analyze_correlation(events, (self.coverage(),))
        self.assertEqual(observation.status, 'continuous')
        self.assertIsNone(observation.recommendation)
        self.assertEqual(observation.enforcement, 'advisory')
        self.assertEqual(observation.lifecycle_class, 'UNKNOWN')

    def test_proven_trace_or_parent_discontinuity_only_recommends_bounded_review(self):
        for downstream, reason in ((self.downstream(trace_id='b' * 32), 'TRACE_MISMATCH'),
                                   (self.downstream(parent_span_id='3' * 16), 'PARENT_MISMATCH'),
                                   (self.downstream(trace_id=None, span_id=None, parent_span_id=None), 'DOWNSTREAM_CONTEXT_ABSENT')):
            with self.subTest(reason=reason):
                observation, = analyze_correlation((self.upstream(), downstream), (self.coverage(),))
                self.assertEqual(observation.status, 'proven_missing_link')
                self.assertEqual(observation.reason, reason)
                self.assertIsNotNone(observation.recommendation)
                self.assertFalse(observation.automatic_fix)
                self.assertEqual(observation.source.status, 'SOURCE_UNRESOLVED')
                self.assertIsNone(observation.source.location)
                self.assertTrue(observation.source.lookup_plan)

    def test_missing_logs_partial_coverage_and_unspecified_propagation_do_not_prove_break(self):
        bad = self.downstream(trace_id='b' * 32)
        for events, coverage in (((self.upstream(),), (self.coverage(),)),
                                  ((self.upstream(), bad), ()),
                                  ((self.upstream(), bad), (self.coverage(downstream_complete=False),)),
                                  ((self.upstream(), bad), (self.coverage(propagation_expected=False),)),
                                  ((self.upstream(), self.downstream(trace_id=None, span_id=None)), (self.coverage(),)),
                                  ((self.upstream(), self.downstream(context_observed=False)), (self.coverage(),))):
            observation, = analyze_correlation(events, coverage)
            self.assertEqual(observation.status, 'unresolved')
            self.assertIsNone(observation.recommendation)

    def test_null_trace_custom_correlation_and_options_message_are_not_trace_proof(self):
        events = (self.upstream(trace_id=None, span_id=None, correlation_id='custom', message='OPTIONS cookie=null'),
                  self.downstream(trace_id=None, span_id=None, parent_span_id=None, correlation_id='custom'))
        observation, = analyze_correlation(events, (self.coverage(),))
        self.assertEqual(observation.status, 'unresolved')
        self.assertIsNone(observation.recommendation)

    def test_matching_correlation_ids_never_join_different_explicit_hops(self):
        events = (self.upstream(pair_id='hop-one', correlation_id='shared'),
                  self.downstream(pair_id='hop-two', correlation_id='shared'))
        coverage = (self.coverage(pair_id='hop-one'), self.coverage(pair_id='hop-two'))
        observations = analyze_correlation(events, coverage)
        self.assertEqual(len(observations), 2)
        self.assertTrue(all(item.status == 'unresolved' and item.recommendation is None for item in observations))
        self.assertEqual(observations, analyze_correlation(tuple(reversed(events)), tuple(reversed(coverage))))

    def test_duplicate_or_conflicting_events_and_duplicate_coverage_are_not_recommended(self):
        for events in ((self.upstream(), self.upstream(event_id='other-out'), self.downstream()),
                       (self.upstream(), self.downstream(event_id='outbound', trace_id='b' * 32))):
            observation, = analyze_correlation(events, (self.coverage(),))
            self.assertEqual(observation.status, 'unresolved')
            self.assertIsNone(observation.recommendation)
        with self.assertRaises(ValueError):
            analyze_correlation((self.upstream(),), (self.coverage(), self.coverage()))

    def test_public_evidence_is_grounded_but_contains_no_identifiers_messages_or_pii(self):
        private = 'alice@example.invalid token=private-fixture-secret'
        events = (self.upstream(event_id=private, pair_id=private, correlation_id=private, message=private),
                  self.downstream(pair_id=private, trace_id='b' * 32, message=private))
        coverage = CorrelationCoverage(private, True, True, True)
        observation, = analyze_correlation(events, (coverage,))
        wire = json.dumps(observation.to_dict())
        for raw in (private, 'alice@example.invalid', 'private-fixture-secret', 'a' * 32, 'b' * 32, '1' * 16):
            self.assertNotIn(raw, wire + repr(events))
        self.assertTrue(observation.runtime_evidence)
        self.assertEqual(observation.source.status, 'SOURCE_UNRESOLVED')
        self.assertEqual(observation.to_dict()['risk_if_changed']['level'], 'unknown')
        self.assertEqual(observation.to_dict()['volume_status'], 'unknown')
        self.assertEqual(observation.to_dict()['consumer_status'], 'unknown')

    def test_strict_w3c_and_boolean_inputs_and_bounded_batch(self):
        for changes in ({'trace_id': '0' * 32}, {'span_id': '0' * 16}, {'trace_id': 'example'},
                        {'side': 'custom'}, {'context_observed': 'unknown'}):
            with self.assertRaises(ValueError):
                self.upstream(**changes)
        for changes in ({'upstream_complete': 1}, {'downstream_complete': None}, {'propagation_expected': 'true'}):
            with self.assertRaises(ValueError):
                self.coverage(**changes)
        with self.assertRaises(ValueError):
            analyze_correlation([self.upstream()], (self.coverage(),))
        with self.assertRaises(ValueError):
            analyze_correlation((self.upstream(),) * 1001, ())

    def test_results_are_deterministic_frozen_and_fresh_json(self):
        events = (self.upstream(), self.downstream(trace_id='b' * 32))
        first = analyze_correlation(events, (self.coverage(),))
        self.assertEqual(first, analyze_correlation(tuple(reversed(events)), (self.coverage(),)))
        with self.assertRaises(FrozenInstanceError):
            first[0].reason = 'changed'
        wire = first[0].to_dict()
        wire['source']['lookup_plan'] = 'modified'
        wire['runtime_evidence'].clear()
        self.assertNotEqual(first[0].to_dict()['source']['lookup_plan'], 'modified')
        self.assertTrue(first[0].to_dict()['runtime_evidence'])

    def test_analysis_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'source.log').write_bytes(b'actual fixture remains unchanged\n')
            (root / 'empty').mkdir()
            before = {p.name: None if p.is_dir() else p.read_bytes() for p in root.iterdir()}
            analyze_correlation((self.upstream(), self.downstream()), (self.coverage(),))
            self.assertEqual(before, {p.name: None if p.is_dir() else p.read_bytes() for p in root.iterdir()})


if __name__ == '__main__':
    unittest.main()
