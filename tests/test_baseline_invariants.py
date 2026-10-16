"""T018 acceptance boundaries independent of producer implementation internals."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from devsift.baseline import (BaselineEntry, BaselineError, BaselineSnapshot, UpdateApproval,
                              diff_snapshots, load_snapshot, save_snapshot)
from devsift.evidence import Region, SourceLocation
from devsift.suppressions import Suppression, SuppressionError, load_suppressions


FIXTURES = Path(__file__).parent / "fixtures" / "baseline"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class BaselineInvariants(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "baseline.json"
        self.sha = "1" * 40
        self.location = SourceLocation("fixture/repo", self.sha, "src/code.py", Region(2, 1, 2, 8))
        self.entry = BaselineEntry("HC001", "rule@1", "a" * 64, self.location)
        self.snapshot = self.snapshot_of((self.entry,))

    def snapshot_of(self, entries=(), tool="tool@1", catalog="rules@1"):
        # Snapshot wire records are reviewed observations, not claims that these
        # fixture SHAs exist. Real Git source capture is covered by producer tests.
        return BaselineSnapshot("fixture/repo", self.sha, tool, catalog, entries)

    def approval(self, snapshot=None, predecessor=None):
        return UpdateApproval("requester", "independent-reviewer", "CHANGE-123",
                              (snapshot or self.snapshot).digest, predecessor)

    def save(self):
        return save_snapshot(self.path, self.snapshot, self.approval())

    def test_recomputed_embedded_digest_cannot_replace_trusted_external_integrity(self):
        trusted = self.save()
        envelope = json.loads(self.path.read_text(encoding="utf-8"))
        altered = self.snapshot_of(())
        envelope["snapshot"] = altered.to_dict()
        envelope["approval"]["approved_digest"] = altered.digest
        envelope["approval"]["actor"] = "attacker"
        self.path.write_text(json.dumps(envelope), encoding="utf-8")
        tampered = self.path.read_bytes()
        with self.assertRaises(BaselineError):
            load_snapshot(self.path, expected_digest=trusted)
        self.assertEqual(self.path.read_bytes(), tampered)
        # Explicitly trusting attacker-controlled bytes defeats the trust model;
        # editable hashes/labels alone are not cryptographic authentication.
        untrusted_digest = hashlib.sha256(tampered).hexdigest()
        self.assertEqual(load_snapshot(self.path, expected_digest=untrusted_digest), altered)

    def test_approval_binds_new_content_and_predecessor_and_requires_distinct_review(self):
        trusted = self.save()
        original = self.path.read_bytes()
        altered = self.snapshot_of(())
        cases = (
            (altered, self.approval(self.snapshot, trusted), trusted),
            (altered, self.approval(altered, trusted), "0" * 64),
            (altered, self.approval(altered), trusted),
            (altered, self.approval(altered), None),
        )
        for snapshot, approval, expected in cases:
            with self.subTest(expected=expected), self.assertRaises(BaselineError):
                save_snapshot(self.path, snapshot, approval, expected_digest=expected)
            self.assertEqual(self.path.read_bytes(), original)
        for actor, reviewer in (("same", "same"), ("same", " SAME ")):
            with self.assertRaises(BaselineError):
                UpdateApproval(actor, reviewer, "CHANGE-123", altered.digest)

    def test_version_migrations_do_not_silently_resolve_or_refresh_findings(self):
        trusted = self.save()
        old = self.path.read_bytes()
        changed_rule = BaselineEntry("HC001", "rule@2", self.entry.fingerprint, self.location)
        for newer in (self.snapshot_of((), tool="tool@2"), self.snapshot_of((), catalog="rules@2"),
                      self.snapshot_of((changed_rule,))):
            with self.subTest(newer=newer), self.assertRaises(BaselineError):
                diff_snapshots(self.snapshot, newer)
        self.assertEqual(load_snapshot(self.path, expected_digest=trusted), self.snapshot)
        self.assertEqual(self.path.read_bytes(), old)

    def test_nested_unknown_fields_duplicate_keys_and_invalid_versions_are_rejected(self):
        valid = self.snapshot.to_dict()
        variants = []
        for branch in ((), ("entries", 0), ("entries", 0, "location"),
                       ("entries", 0, "location", "region")):
            data = deepcopy(valid)
            target = data
            for key in branch:
                target = target[key]
            target["unknown"] = True
            variants.append(data)
        variants.extend([valid | {"schema_version": "2"}, valid | {"schema_version": True},
                         valid | {"entries": [valid["entries"][0], valid["entries"][0]]}])
        for data in variants:
            with self.subTest(data=data), self.assertRaises(BaselineError):
                BaselineSnapshot.from_json(json.dumps(data))
        text = self.snapshot.to_json().replace('"rule_version":"rule@1"',
                                               '"rule_version":"rule@1","rule_version":"rule@1"')
        with self.assertRaises(BaselineError):
            BaselineSnapshot.from_json(text)

    def test_load_diff_and_returned_copies_have_no_filesystem_or_input_mutation(self):
        trusted = self.save()
        before = {path.name: path.read_bytes() for path in self.path.parent.iterdir()}
        loaded = load_snapshot(self.path, expected_digest=trusted)
        wire = loaded.to_dict()
        wire["entries"][0]["location"]["region"]["start_line"] = 999
        self.assertEqual(loaded.entries[0].location.region.start_line, 2)
        delta = diff_snapshots(loaded, loaded)
        self.assertEqual((delta.added, delta.resolved), ((), ()))
        self.assertEqual(delta.unchanged, (self.entry,))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.path.parent.iterdir()})

    def test_trusted_digest_does_not_bypass_strict_envelope_and_approval_schema(self):
        self.save()
        original = json.loads(self.path.read_text(encoding="utf-8"))
        invalid = []
        for branch in ((), ("approval",)):
            data = deepcopy(original)
            target = data
            for key in branch:
                target = target[key]
            target["unknown"] = True
            invalid.append(json.dumps(data))
        data = deepcopy(original)
        data["schema_version"] = "2"
        invalid.append(json.dumps(data))
        data = deepcopy(original)
        data["approval"]["expected_digest"] = True
        invalid.append(json.dumps(data))
        invalid.append(json.dumps(original).replace('"reviewer": "independent-reviewer"',
                        '"reviewer": "independent-reviewer", "reviewer": "independent-reviewer"'))
        for text in invalid:
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                raw = self.path.read_bytes()
                with self.assertRaises(BaselineError):
                    load_snapshot(self.path, expected_digest=hashlib.sha256(raw).hexdigest())
                self.assertEqual(self.path.read_bytes(), raw)

    def test_suppression_fixture_rejects_critical_floor_and_blanket_or_invalid_scope(self):
        valid = fixture("valid-suppression.json")
        original = deepcopy(valid)
        for case in fixture("invalid-suppressions.json"):
            with self.subTest(name=case["name"]), self.assertRaises(SuppressionError):
                Suppression.from_dict(valid | case["patch"])
        self.assertEqual(valid, original)

    def test_suppression_expiry_is_timezone_deterministic_and_never_uses_ambient_time(self):
        data = fixture("valid-suppression.json")
        expiry_utc = datetime(2026, 10, 17, 17, tzinfo=timezone.utc)
        before = datetime(2026, 10, 17, 16, 59, 59, tzinfo=timezone.utc)
        suppression = Suppression.from_dict(data)
        self.assertTrue(suppression.matches("HC001", "a" * 64, as_of=before))
        self.assertFalse(suppression.matches("HC003", "a" * 64, as_of=before))
        self.assertFalse(suppression.matches("HC001", "b" * 64, as_of=before))
        for moment in (expiry_utc, datetime(2026, 10, 18, tzinfo=timezone.utc), datetime(2026, 10, 16)):
            with self.subTest(moment=moment), self.assertRaises(SuppressionError):
                load_suppressions(json.dumps([data]), as_of=moment)
        with self.assertRaises(SuppressionError):
            load_suppressions(json.dumps([data, data]), as_of=before)
        duplicate = json.dumps([data]).replace('"owner": "platform-team"',
                                               '"owner": "platform-team", "owner": "platform-team"')
        with self.assertRaises(SuppressionError):
            load_suppressions(duplicate, as_of=before)


if __name__ == "__main__":
    unittest.main()
