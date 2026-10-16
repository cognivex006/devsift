from dataclasses import FrozenInstanceError
import unittest

from devsift.adapters import AdapterCapability, detect_language, negotiate
from devsift.inventory import SourceTarget


class AdapterTests(unittest.TestCase):
    def test_detection(self):
        for name, language in (('a.cs', 'csharp'), ('a.tsx', 'typescript'),
                               ('a.js', 'javascript'), ('a.go', 'go'), ('a.sql', 'sql'),
                               ('a.PY', 'python'), ('a.txt', None)):
            self.assertEqual(detect_language(name), language)

    def test_missing_analyzers_are_unavailable_not_pass(self):
        target = SourceTarget('a.ts', 'ready', 'typescript', b'const a = 1;', '')
        self.assertEqual(negotiate(target).status, 'unavailable')
        cap = AdapterCapability('typescript-native', '1.0', ('typescript',), False)
        decision = negotiate(target, (cap,))
        self.assertEqual(decision.status, 'unavailable')
        self.assertEqual(decision.adapter_id, 'typescript-native')
        self.assertEqual(decision.version, '1.0')

    def test_available_negotiation_is_not_analysis(self):
        target = SourceTarget('a.ts', 'ready', 'typescript', b'const a = 1;', '')
        cap = AdapterCapability('typescript-native', '1.0', ('typescript',), True)
        decision = negotiate(target, (cap,))
        self.assertEqual(decision.status, 'supported')
        self.assertNotIn('clean', decision.reason)
        with self.assertRaises(FrozenInstanceError):
            cap.available = False

    def test_selection_is_deterministic_and_prefers_available(self):
        target = SourceTarget('a.go', 'ready', 'go', b'package main', '')
        unavailable = AdapterCapability('a', '1', ('go',), False)
        available = AdapterCapability('z', '2', ('go',), True)
        first = negotiate(target, (unavailable, available))
        self.assertEqual(first, negotiate(target, (available, unavailable)))
        self.assertEqual(first.adapter_id, 'z')

    def test_skipped_and_unresolved_are_distinct(self):
        for status, expected in (('unsupported', 'skipped'), ('binary', 'skipped'),
                                 ('excluded', 'skipped'), ('unreadable', 'incomplete'),
                                 ('unsafe', 'incomplete'), ('missing', 'incomplete')):
            self.assertEqual(negotiate(SourceTarget('a', status, None, None, '')).status, expected)

    def test_invalid_and_duplicate_capabilities_rejected(self):
        for args in (('', '1', ('go',), True), ('go', '', ('go',), True),
                     ('go', '1', ('go',), 'unknown'), ('go', '1', ['go'], True)):
            with self.assertRaises(ValueError):
                AdapterCapability(*args)
        cap = AdapterCapability('go', '1', ('go',), True)
        with self.assertRaises(ValueError):
            negotiate(SourceTarget('a.go', 'ready', 'go', b'x', ''), (cap, cap))


if __name__ == '__main__':
    unittest.main()
