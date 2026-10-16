from datetime import datetime, timezone
import unittest

from devsift.suppressions import Suppression, SuppressionError, load_suppressions


class SuppressionTests(unittest.TestCase):
    def suppression(self, **changes):
        data = {"schema_version": "1", "rule_id": "HC001", "fingerprint": "a" * 64,
                "owner": "team", "reason": "bounded approved exception", "ticket": "ISSUE-1",
                "expires_at": "2026-10-17T00:00:00Z"}
        data.update(changes)
        return Suppression.from_dict(data)

    def test_scope_roundtrip_and_expiry_at_exact_timezone_aware_boundary(self):
        suppression = self.suppression()
        before = datetime(2026, 10, 16, tzinfo=timezone.utc)
        boundary = datetime(2026, 10, 17, tzinfo=timezone.utc)
        self.assertEqual(Suppression.from_dict(suppression.to_dict()), suppression)
        self.assertTrue(suppression.matches("HC001", "a" * 64, as_of=before))
        self.assertFalse(suppression.matches("HC001", "b" * 64, as_of=before))
        for moment in (boundary, datetime(2026, 10, 16)):
            with self.assertRaises(SuppressionError):
                suppression.matches("HC001", "a" * 64, as_of=moment)

    def test_critical_waivers_and_invalid_or_blanket_scope_are_rejected(self):
        for changes in ({"rule_id": "HC002"}, {"rule_id": "SEC003"}, {"rule_id": "*"},
                        {"fingerprint": "*"}, {"owner": " "}, {"reason": ""}, {"ticket": ""},
                        {"expires_at": "2026-10-17"}, {"expires_at": True}, {"extra": 1},
                        {"schema_version": 1}):
            with self.subTest(changes=changes), self.assertRaises(SuppressionError):
                self.suppression(**changes)

    def test_strict_collection_load_rejects_expired_duplicate_and_unknown_fields(self):
        import json
        valid = self.suppression().to_dict()
        before = datetime(2026, 10, 16, tzinfo=timezone.utc)
        self.assertEqual(load_suppressions(json.dumps([valid]), as_of=before), (self.suppression(),))
        for text in (json.dumps([valid, valid]), '[{"schema_version":"1","schema_version":"1"}]',
                     json.dumps([valid | {"extra": True}])):
            with self.assertRaises(SuppressionError):
                load_suppressions(text, as_of=before)
        with self.assertRaises(SuppressionError):
            load_suppressions(json.dumps([valid]), as_of=datetime(2026, 10, 18, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
