"""T027 actual frontend fixtures and bounded changed-scope integration."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import devsift.inventory as inventory_module
from devsift.cli_scan import run_scan
from devsift.inventory import SourceTarget
from devsift.native_host import NativeAdapter, analyze_snapshot, probe_tool
from devsift.scanner import scan
from devsift.typescript_adapter import make_tool


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "frontend"


@unittest.skipUnless(os.environ.get("DEVSIFT_TEST_NATIVE") == "1", "requires explicit pinned frontend setup")
class FrontendAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        executable = os.environ.get("DEVSIFT_NODE_EXECUTABLE") or shutil.which("node")
        if not executable:
            raise AssertionError("requested frontend acceptance requires Node")
        package = Path(os.environ.get("DEVSIFT_FRONTEND_PACKAGE", str(ROOT / "native/frontend"))).resolve()
        cls.tool = make_tool(str(Path(executable).resolve()), package)
        if not probe_tool(cls.tool).available:
            raise AssertionError("requested frontend acceptance requires installed pinned dependencies")

    def report(self, text, path="src/client.ts"):
        return analyze_snapshot(self.tool, SourceTarget(path, "ready", "typescript", text.encode(), ""))

    def git(self, root, *arguments):
        return subprocess.run(["git", "-C", str(root), *arguments], capture_output=True,
                              text=True, check=True).stdout.strip()

    def initialize(self, root):
        self.git(root, "init", "-q")
        self.git(root, "config", "user.email", "fixture@example.invalid")
        self.git(root, "config", "user.name", "Frontend Acceptance")
        self.git(root, "config", "core.autocrlf", "false")

    def test_angular_next_and_context_negatives_use_actual_estree_analysis(self):
        for file, path in (("angular.component.ts", "src/app/card.component.ts"), ("next-page.tsx", "app/page.tsx")):
            with self.subTest(file=file):
                report = self.report((FIXTURES / file).read_text(encoding="utf-8"), path)
                self.assertTrue(report.complete)
                self.assertEqual(report.diagnostics, ())
        cases = json.loads((FIXTURES / "context-cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                report = self.report(case["source"], case["path"])
                self.assertTrue(report.complete)
                self.assertEqual([item.rule_id for item in report.diagnostics], case["rules"])

    def test_changed_cli_selection_never_reads_or_analyzes_unchanged_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root)
            for name, text in {"client.ts": "export const value=1;", "environment.ts": "export const config=1;",
                               "legacy.ts": "fetch('https://legacy.example.test');"}.items():
                (root / name).write_text(text, encoding="utf-8")
            self.git(root, "add", "client.ts", "environment.ts", "legacy.ts")
            self.git(root, "commit", "-qm", "fixture")
            sha = self.git(root, "rev-parse", "HEAD")
            (root / "environment.ts").write_text("fetch('https://config.example.test');", encoding="utf-8")
            self.git(root, "add", "environment.ts")
            (root / "client.ts").write_text("fetch('https://runtime.example.test');", encoding="utf-8")
            (root / "page.tsx").write_text("export default ()=> <span>safe</span>;", encoding="utf-8")
            native = NativeAdapter(self.tool, repo_root=root, source_sha=sha)
            analyzed = []

            class RecordingAdapter:
                capability = native.capability

                def analyze(self, target):
                    analyzed.append(target.path)
                    return native.analyze(target)

            def execute(selected_root, candidates, *, adapters=()):
                # No manifest was supplied to run_scan: explicitly configured
                # native CLI support must not auto-discover any tool here.
                self.assertEqual(adapters, ())
                return scan(selected_root, candidates, adapters=(RecordingAdapter(),))

            before = self.git(root, "status", "--porcelain")
            original_read = inventory_module._read_bytes
            with patch("devsift.cli_scan.scan", side_effect=execute), \
                    patch("devsift.inventory._read_bytes", wraps=original_read) as reads:
                record = run_scan(root)
            expected = {"client.ts", "environment.ts", "page.tsx"}
            self.assertEqual(set(analyzed), expected)
            self.assertEqual({item["path"] for item in record["data"]["targets"]}, expected)
            read_paths = {call.args[0].name for call in reads.call_args_list}
            self.assertEqual(read_paths, expected)
            self.assertNotIn("legacy.ts", read_paths)
            self.assertEqual(record["exit_code"], 2)
            self.assertEqual(record["enforced_count"], 0)
            self.assertEqual([finding["rule_id"] for finding in record["findings"]], ["HC001"])
            self.assertEqual(record["findings"][0]["lifecycle_class"], "UNKNOWN")
            self.assertEqual(record["findings"][0]["source"]["status"], "SOURCE_UNRESOLVED")
            self.assertEqual(self.git(root, "status", "--porcelain"), before)

    def test_committed_credential_keeps_unknown_source_proof_mask_and_security_review(self):
        secret = "acceptance" + "SensitiveValue"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.initialize(root)
            (root / "client.ts").write_text("const apiKey='" + secret + "';", encoding="utf-8")
            self.git(root, "add", "client.ts")
            self.git(root, "commit", "-qm", "fixture")
            sha = self.git(root, "rev-parse", "HEAD")
            native = NativeAdapter(self.tool, repo_root=root, source_sha=sha)
            record = scan(root, ("client.ts",), adapters=(native,))
            self.assertEqual(record["exit_code"], 2)
            self.assertEqual(record["enforced_count"], 0)
            finding = record["findings"][0]
            self.assertEqual(finding["source"]["status"], "VERIFIED")
            self.assertEqual(finding["source"]["before"], "[REDACTED]")
            self.assertEqual(finding["lifecycle_class"], "UNKNOWN")
            self.assertTrue(finding["security_escalation"])
            self.assertNotIn(secret, json.dumps(record))

    def test_real_ast_workload_and_large_source_use_file_transport(self):
        source = "".join(f"export const row{index}: number = {index};\n" for index in range(3500))
        self.assertEqual(self.tool.process.timeout_seconds, 30)
        started = time.perf_counter()
        report = self.report(source)
        elapsed = time.perf_counter() - started
        print(f"FRONTEND_BUDGET bytes={len(source.encode())} declarations=3500 elapsed_seconds={elapsed:.3f} process_budget=30 environment_budget=90")
        self.assertTrue(report.complete)
        self.assertEqual(report.diagnostics, ())
        self.assertLess(elapsed, 90)  # Includes host contention; not a throughput benchmark.
        large_source = "//" + "x" * 2_000_001
        large = self.report(large_source)
        self.assertTrue(large.complete)
        self.assertEqual(large.diagnostics, ())
        legacy = analyze_snapshot(self.tool, SourceTarget(
            'fixture.ts', 'ready', 'typescript', large_source.encode(), ''), transports=('inline',))
        self.assertFalse(legacy.complete)
        self.assertEqual(legacy.diagnostics, ())

    def test_source_imports_and_customer_configs_are_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "must-not-exist"
            side_effect = "require('node:fs').writeFileSync(" + json.dumps(str(marker)) + ",'executed');"
            (root / "side-effect.cjs").write_text(side_effect, encoding="utf-8")
            (root / "eslint.config.cjs").write_text(side_effect, encoding="utf-8")
            (root / "tsconfig.json").write_text("invalid target config; must not load", encoding="utf-8")
            source = "import './side-effect.cjs'; export const value=1;"
            (root / "client.ts").write_text(source, encoding="utf-8")
            before = {item.name: item.read_bytes() for item in root.iterdir()}
            report = self.report(source)
            self.assertTrue(report.complete)
            request = {"protocol_version": "1", "path": "client.ts", "language": "typescript",
                       "source": source, "dialect": None}
            # Even direct invocation from a customer cwd must ignore executable
            # ESLint config/import side effects, not merely rely on runner cwd.
            direct = subprocess.run([self.tool.process.executable, *self.tool.process.argv, "--analyze"],
                                    input=json.dumps(request), capture_output=True, text=True,
                                    encoding="utf-8", cwd=root, timeout=30, check=True)
            self.assertTrue(json.loads(direct.stdout)["complete"])
            self.assertFalse(marker.exists())
            self.assertEqual(before, {item.name: item.read_bytes() for item in root.iterdir()})


if __name__ == "__main__":
    unittest.main()
