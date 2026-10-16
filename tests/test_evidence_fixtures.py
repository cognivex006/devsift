"""T009: external wire fixtures preserve proof, uncertainty and proposal roles."""
import copy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from devsift.evidence import (
    AfterProposal, EvidenceError, Region, RuntimeEvidence, SourceEvidence,
    verify_source,
)
from devsift.redaction import Redactor


FIXTURES = Path(__file__).parent / "fixtures" / "evidence"


class EvidenceFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.repo = Path(cls.temp.name)
        cls.git("init", "-q")
        cls.git("config", "user.name", "Evidence Contract Fixture")
        cls.git("config", "user.email", "fixture@example.invalid")
        cls.git("config", "core.autocrlf", "false")
        cls.sensitive = "fixture" + "SensitiveOnlyValue"
        cls.content = "safe = 1\npassword='" + cls.sensitive + "'\n"
        (cls.repo / "sample.py").write_bytes(cls.content.encode("utf-8"))
        cls.git("add", "sample.py")
        cls.git("commit", "-qm", "contract fixture")
        cls.sha = cls.git("rev-parse", "HEAD").strip()
        cls.wires = json.loads((FIXTURES / "wire-records.json").read_text(encoding="utf-8"))
        cls.wires["verified"]["location"]["source_sha"] = cls.sha

    @classmethod
    def git(cls, *arguments):
        return subprocess.run(
            ["git", "-C", str(cls.repo), *arguments], check=True,
            capture_output=True, text=True, encoding="utf-8",
        ).stdout

    def restore(self, kind, wire):
        factories = {
            "runtime": RuntimeEvidence.from_dict,
            "proposal": AfterProposal.from_dict,
            "unresolved": SourceEvidence.from_dict,
            "verified": lambda value: SourceEvidence.from_dict(value, repo_root=self.repo),
        }
        return factories[kind](wire)

    def test_fixture_round_trips_both_directions_without_aliases(self):
        for kind, expected in self.wires.items():
            with self.subTest(kind=kind):
                encoded = json.loads(json.dumps(expected, ensure_ascii=False))
                record = self.restore(kind, encoded)
                self.assertEqual(record.to_dict(), expected)
                encoded.clear()
                self.assertEqual(record.to_dict(), expected)
                public = record.to_dict()
                if kind == "verified":
                    public["location"]["region"]["start_line"] = 999
                else:
                    public.clear()
                self.assertEqual(record.to_dict(), expected)
                with self.assertRaises(FrozenInstanceError):
                    record.contract_fixture = True

    def test_source_and_runtime_and_proposal_roles_are_not_interchangeable(self):
        for source_kind, wire in self.wires.items():
            for destination in ("verified", "unresolved", "runtime", "proposal"):
                if {source_kind, destination} <= {"verified", "unresolved"}:
                    continue
                if source_kind == destination:
                    continue
                with self.subTest(source=source_kind, destination=destination):
                    with self.assertRaises(EvidenceError):
                        self.restore(destination, copy.deepcopy(wire))

    def test_wire_fields_cannot_invent_source_or_promote_proposals(self):
        mutations = json.loads((FIXTURES / "rejected-wire-fields.json").read_text())
        for mutation in mutations:
            kind = mutation["kind"]
            wire = copy.deepcopy(self.wires[kind])
            wire[mutation["field"]] = mutation["value"]
            with self.subTest(mutation=mutation):
                with self.assertRaises(EvidenceError):
                    self.restore(kind, wire)

    def test_verified_wire_requires_live_immutable_proof_not_a_status_label(self):
        wire = copy.deepcopy(self.wires["verified"])
        with self.assertRaises(EvidenceError):
            SourceEvidence.from_dict(wire)
        for change in ("before", "commit"):
            invalid = copy.deepcopy(wire)
            if change == "before":
                invalid["before"] = self.wires["proposal"]["code"]
            else:
                invalid["location"]["source_sha"] = "0" * 40
            with self.subTest(change=change):
                result = SourceEvidence.from_dict(invalid, repo_root=self.repo)
                self.assertEqual(result.status, "SOURCE_UNRESOLVED")
                self.assertIsNone(result.location)
                self.assertIsNone(result.before)

    def test_nested_region_and_symbol_tampering_cannot_claim_proof(self):
        for key, value in (("start_line", True), ("start_column", 0),
                           ("end_line", 0), ("end_column", -1)):
            wire = copy.deepcopy(self.wires["verified"])
            wire["location"]["region"][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                SourceEvidence.from_dict(wire, repo_root=self.repo)
        for key, value in (("symbol", "Invented.Symbol"), ("path", "../outside.py")):
            wire = copy.deepcopy(self.wires["verified"])
            wire["location"][key] = value
            with self.subTest(key=key), self.assertRaises(EvidenceError):
                SourceEvidence.from_dict(wire, repo_root=self.repo)

    def test_sensitive_clipped_before_round_trips_without_becoming_a_proposal(self):
        result = verify_source(
            self.repo, "fixture/repository", self.sha, "sample.py",
            Region(2, 11, 2, 11 + len(self.sensitive)),
        )
        self.assertEqual(result.status, "VERIFIED")
        self.assertEqual(result.before, "[REDACTED]")
        wire = json.loads(json.dumps(result.to_dict()))
        restored = SourceEvidence.from_dict(wire, repo_root=self.repo)
        self.assertEqual(restored, result)
        self.assertNotIn(self.sensitive, repr(restored) + json.dumps(wire))
        with self.assertRaises(EvidenceError):
            AfterProposal.from_dict(wire)
        unresolved = copy.deepcopy(self.wires["unresolved"])
        unresolved["lookup_plan"] = self.sensitive
        redactor = Redactor((self.sensitive,))
        masked = SourceEvidence.from_dict(unresolved, redactor=redactor)
        self.assertEqual(masked.lookup_plan, "[REDACTED]")

    def test_verification_round_trips_do_not_write_source_or_git_metadata(self):
        def snapshot():
            return {str(path.relative_to(self.repo)): path.read_bytes()
                    for path in self.repo.rglob("*") if path.is_file()}
        before = snapshot()
        for kind, wire in self.wires.items():
            self.restore(kind, copy.deepcopy(wire)).to_dict()
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
