"""Actual filesystem discovery, private failures and accepted gate invariants."""
from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devsift.policy import decide, resolve_policy
from devsift.project_policy import discover_policy


class ProjectPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / ".devsift" / "policy.json"
        self.source = self.root / "sample.py"
        self.source.write_text("print('untouched')\n", encoding="utf-8")

    def write(self, text):
        self.path.parent.mkdir(exist_ok=True)
        self.path.write_bytes(text.encode("utf-8"))

    def test_missing_default_defaults_but_explicit_missing_and_missing_root_fail(self):
        result = discover_policy(self.root)
        self.assertTrue(result.complete)
        self.assertEqual(result.policy(), resolve_policy())
        self.assertIsNone(result.relative_path)
        self.assertIsNone(result.raw_sha256)
        self.assertFalse(discover_policy(self.root, policy_path="missing.json").complete)
        self.assertFalse(discover_policy(self.root / "missing-root").complete)

    def test_partial_project_override_provenance_and_fresh_immutable_results(self):
        raw = '{"rules":{"HC001":{"severity":"Error"}}}'
        self.write(raw)
        result = discover_policy(self.root)
        self.assertTrue(result.complete)
        self.assertEqual(result.relative_path, ".devsift/policy.json")
        self.assertEqual(result.raw_sha256, hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(result.policy()["rules"]["HC001"]["severity"], "Error")
        output = result.to_dict()
        output["policy"]["rules"]["HC001"]["severity"] = "Suggestion"
        self.assertEqual(result.policy()["rules"]["HC001"]["severity"], "Error")
        self.assertNotIn(str(self.root), json.dumps(result.to_dict()))
        self.assertFalse(result.write_authorized)
        self.assertFalse(result.execution_authorized)
        with self.assertRaises(FrozenInstanceError):
            result.complete = False

    def test_explicit_local_path_only_no_ancestor_or_global_search(self):
        (self.root / "chosen.json").write_text('{"quality_gate":{"block_on":[]}}', encoding="utf-8")
        explicit = discover_policy(self.root, policy_path="chosen.json")
        self.assertTrue(explicit.complete)
        self.assertEqual(explicit.relative_path, "chosen.json")
        self.assertEqual(explicit.policy()["quality_gate"]["block_on"], [])
        child = self.root / "child"
        child.mkdir()
        self.write('{"quality_gate":{"block_on":[]}}')
        self.assertEqual(discover_policy(child).policy(), resolve_policy())
        for value in ("../chosen.json", "/chosen.json", "C:/chosen.json", "a\\chosen.json",
                      "a/../chosen.json", "./chosen.json", "a//chosen.json", "https://host/policy.json",
                      "chosen.py", True, [], ".git/config.json", "a\n/policy.json"):
            with self.subTest(value=value):
                self.assertFalse(discover_policy(self.root, policy_path=value).complete)

    def test_present_malformed_never_falls_back_and_no_private_value_echo(self):
        private = "ghp_" + "Ab8" * 12
        invalid = ["null", "[]", "{", '{"rules":{"HC001":{"severity":"' + private + '"}}}',
                   '{"rules":{},"rules":{}}', '{"quality_gate":{"block_on":[],"block_on":[]}}',
                   '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":' + "9" * 1000 + '}',
                   '{"x":' + "[" * 30 + "0" + "]" * 30 + '}',
                   '{"native_manifest":"execute.json"}', '{"permissions":{"write":true}}',
                   '{"schema_version":true}', " " * 65537]
        for raw in invalid:
            self.write(raw)
            result = discover_policy(self.root)
            with self.subTest(raw=raw[:15]):
                self.assertFalse(result.complete)
                self.assertIsNone(result.policy())
                self.assertNotIn(private, repr(result))
                self.assertNotIn(private, json.dumps(result.to_dict()))
        self.path.write_bytes(b"\xff\xfeinvalid")
        self.assertFalse(discover_policy(self.root).complete)

    def test_actual_policy_legacy_unknown_and_critical_security_floor(self):
        self.write('{"rules":{"SEC001":{"severity":"Suggestion"},"HC001":{"severity":"Error"}}}')
        policy = discover_policy(self.root).policy()
        self.assertEqual(decide("HC001", "NEW", source_verified=True, policy=policy).enforcement, "block")
        self.assertEqual(decide("HC001", "LEGACY_UNCHANGED", source_verified=True, policy=policy).enforcement, "advisory")
        self.assertEqual(decide("HC001", "UNKNOWN", source_verified=True, policy=policy).enforcement, "incomplete")
        self.assertEqual(decide("SEC001", "LEGACY_UNCHANGED", source_verified=True, policy=policy).enforcement,
                         "security_review")

    def test_actual_git_metadata_case_and_win32_aliases_are_never_policy_roots(self):
        base = self.root / ".git"
        base.mkdir()
        (base / "policy.json").write_text("{}", encoding="utf-8")
        for component in (".git", ".GiT", ".GIT", ".GiT.", ".GiT ", ".GIT. "):
            directory = self.root / component
            if os.name != "nt":
                directory.mkdir(exist_ok=True)
                (directory / "policy.json").write_text("{}", encoding="utf-8")
            with self.subTest(component=component):
                result = discover_policy(self.root, policy_path=component + "/policy.json")
                self.assertFalse(result.complete)
                self.assertIsNone(result.policy())
                self.assertFalse(discover_policy(directory).complete)
        # A similarly named ordinary directory is not Git metadata.
        ordinary = self.root / ".gitfoo"
        ordinary.mkdir()
        (ordinary / "policy.json").write_text("{}", encoding="utf-8")
        self.assertTrue(discover_policy(self.root, policy_path=".gitfoo/policy.json").complete)

    @unittest.skipUnless(os.name == "nt", "Windows metadata short alias contract")
    def test_actual_git_metadata_short_alias_rejects_when_available(self):
        import ctypes
        directory = self.root / ".git"
        directory.mkdir()
        (directory / "policy.json").write_text("{}", encoding="utf-8")
        get_short = ctypes.windll.kernel32.GetShortPathNameW
        get_short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        get_short.restype = ctypes.c_uint
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_short(str(directory), buffer, len(buffer))
        self.assertTrue(0 < length < len(buffer))
        component = Path(buffer.value).name
        if component.casefold() == ".git":
            self.skipTest("Filesystem has no distinct short alias for Git metadata")
        self.assertFalse(discover_policy(self.root, policy_path=component + "/policy.json").complete)
        self.assertFalse(discover_policy(buffer.value).complete)

    def test_actual_symlinks_and_directory_instead_of_file_reject(self):
        self.path.parent.mkdir()
        self.path.mkdir()
        self.assertFalse(discover_policy(self.root).complete)
        self.path.rmdir()
        target = self.root / "outside.json"
        target.write_text("{}", encoding="utf-8")
        try:
            self.path.symlink_to(target)
        except OSError:
            self.skipTest("Host does not permit symlink creation")
        self.assertFalse(discover_policy(self.root).complete)
        self.path.unlink()
        self.path.parent.rmdir()
        outside = self.root / "elsewhere"
        outside.mkdir()
        (outside / "policy.json").write_text("{}", encoding="utf-8")
        self.path.parent.symlink_to(outside, target_is_directory=True)
        self.assertFalse(discover_policy(self.root).complete)

    def test_no_process_or_loader_execution_and_source_bytes_unchanged(self):
        self.write("{}")
        before = {p.relative_to(self.root).as_posix(): p.read_bytes()
                  for p in self.root.rglob("*") if p.is_file()}
        with patch("subprocess.run", side_effect=AssertionError("process forbidden")), \
             patch("importlib.import_module", side_effect=AssertionError("code loading forbidden")):
            self.assertTrue(discover_policy(self.root).complete)
        after = {p.relative_to(self.root).as_posix(): p.read_bytes()
                 for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_success_and_failure_release_all_file_and_directory_handles(self):
        for raw in ("{}", "{", " " * 65537):
            self.write(raw)
            discover_policy(self.root)
            renamed = self.path.with_name("renamed.json")
            self.path.rename(renamed)
            renamed.write_text("{}", encoding="utf-8")
            renamed.rename(self.path)
            directory = self.path.parent.with_name("moved-directory")
            self.path.parent.rename(directory)
            directory.rename(self.path.parent)

    @unittest.skipUnless(os.name == "nt", "Windows handle-sharing contract")
    def test_actual_windows_handles_prevent_write_and_parent_replacement_during_read(self):
        self.write("{}")
        original_read = os.read
        attempted = []
        def racing_read(fd, count):
            if not attempted:
                attempted.append(True)
                with self.assertRaises(PermissionError):
                    self.path.write_bytes(b"changed")
                with self.assertRaises(PermissionError):
                    self.path.parent.rename(self.root / "replacement")
            return original_read(fd, count)
        with patch("devsift.project_policy.os.read", side_effect=racing_read):
            self.assertTrue(discover_policy(self.root).complete)
        self.assertTrue(attempted)
        self.assertEqual(self.path.read_bytes(), b"{}")

    @unittest.skipUnless(os.name == "nt", "Windows short-path alias contract")
    def test_actual_windows_short_root_alias_canonicalizes_after_guard(self):
        import ctypes
        self.write("{}")
        get_short = ctypes.windll.kernel32.GetShortPathNameW
        get_short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        get_short.restype = ctypes.c_uint
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_short(str(self.root), buffer, len(buffer))
        self.assertTrue(0 < length < len(buffer))
        if buffer.value.lower() == str(self.root).lower():
            self.skipTest("Filesystem has no distinct short alias for this directory")
        result = discover_policy(buffer.value)
        self.assertTrue(result.complete)
        self.assertEqual(result.relative_path, ".devsift/policy.json")
        self.assertEqual(result.policy(), resolve_policy())

    @unittest.skipUnless(os.name != "nt", "POSIX nofollow descriptor contract")
    def test_actual_posix_replacement_after_open_cannot_redirect_read(self):
        self.write("{}")
        original_read = os.read
        attempted = []
        def racing_read(fd, count):
            if not attempted:
                attempted.append(True)
                self.path.rename(self.path.with_name("old.json"))
                self.path.write_text('{"quality_gate":{"block_on":[]}}', encoding="utf-8")
            return original_read(fd, count)
        with patch("devsift.project_policy.os.read", side_effect=racing_read):
            self.assertFalse(discover_policy(self.root).complete)


if __name__ == "__main__":
    unittest.main()
