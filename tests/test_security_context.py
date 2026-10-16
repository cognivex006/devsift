import json
from pathlib import Path
import subprocess
import ssl
import tempfile
import unittest

from devsift.inventory import SourceTarget
from devsift.scanner import scan
from devsift.security_adapter import SecurityAdapter
from devsift.security_context import python_contexts


PAT = "ghp_" + "Ab7" * 12


class PythonSecurityContexts(unittest.TestCase):
    def test_actual_ssl_verified_override_is_not_an_unverified_configuration(self):
        context = ssl._create_unverified_context(cert_reqs=ssl.CERT_REQUIRED, check_hostname=True)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        source = "import ssl\nssl._create_unverified_context(cert_reqs=ssl.CERT_REQUIRED,check_hostname=True)"
        report = python_contexts(source)
        self.assertTrue(report.complete)
        self.assertEqual(report.diagnostics, ())
        restored = "from ssl import _create_unverified_context as build,CERT_REQUIRED as required\nbuild(check_hostname=True,cert_reqs=required)"
        self.assertEqual(python_contexts(restored).diagnostics, ())
        self.assertTrue(python_contexts(restored).complete)
        unknown = "import ssl\nssl._create_unverified_context(cert_reqs=mode,check_hostname=True)"
        self.assertFalse(python_contexts(unknown).complete)

    def test_known_module_alias_member_override_invalidates_all_aliases(self):
        for source in ("import logging\nalias=logging\nalias.error=lambda *a:None\nlogging.error('" + PAT + "')",
                       "import logging\ndef f():\n logging.error('" + PAT + "')\nalias=logging\nalias.error=lambda *a:None"):
            with self.subTest(source=source):
                report = python_contexts(source)
                self.assertFalse(report.complete)
                self.assertEqual(report.diagnostics, ())

    def rules(self, text):
        report = python_contexts(text)
        self.assertTrue(report.complete)
        return [finding.rule_id for finding in report.diagnostics]

    def test_actual_logging_alias_logger_and_builtin_print_with_proven_values(self):
        sources = ["import logging as log\nlog.error('" + PAT + "')",
                   "from logging import info as record\nrecord('" + PAT + "')",
                   "import logging\nlogger=logging.getLogger(__name__)\ncredential='" + PAT + "'\nlogger.info('%s',credential)",
                   "def handler():\n credential='" + PAT + "'\n print(credential)\n"]
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(self.rules(source), ["SEC001"])

    def test_logging_names_lookalikes_placeholders_sanitized_and_scope_shadows_are_not_critical(self):
        sources = ["import logging\nlogging.error('password missing')",
                   "import logging\nlogging.error('[REDACTED]')",
                   "import logging\nlogging.error('YOUR_API_KEY')",
                   "import other as logging\nlogging.error('" + PAT + "')",
                   "def f(print):\n print('" + PAT + "')\n",
                   "import logging\ndef f(logging):\n logging.error('" + PAT + "')\n",
                   "import logging\nlogging=object()\nlogging.error('" + PAT + "')",
                   "import logging\nx='" + PAT + "'\nlogging.info(redact(x))",
                   "x='" + PAT + "'\ndef f():\n print(x)\n"]
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(self.rules(source), [])

    def test_import_bound_requests_and_ssl_contexts_require_actual_false(self):
        positives = ["import requests as client\nclient.get('https://example.invalid',verify=False)",
                     "from requests import get as fetch\nfetch('https://example.invalid',verify=False)",
                     "import requests\ns=requests.Session()\ns.verify=False",
                     "import requests\ns=requests.Session()\ns.verify=True\ns.headers={}\ns.verify=False",
                     "import ssl as tls\ntls._create_unverified_context()"]
        negatives = ["import requests\nrequests.get('https://example.invalid',verify=True)",
                     "import requests\nrequests.get('https://example.invalid',verify='false')",
                     "import other as requests\nrequests.get('https://example.invalid',verify=False)",
                     "import requests\ndef f(requests):\n requests.get('https://example.invalid',verify=False)\n",
                     "import ssl\nssl.create_default_context()"]
        for source in positives:
            with self.subTest(source=source): self.assertEqual(self.rules(source), ["SEC002"])
        for source in negatives:
            with self.subTest(source=source): self.assertEqual(self.rules(source), [])

    def test_unknown_flow_syntax_and_scope_do_not_become_supported_security_claims(self):
        for source in ("def broken(", "from custom import *\nprint('" + PAT + "')",
                       "import logging\ndef f():\n logging.error('" + PAT + "')\nlogging=object()\n",
                       "def f():\n print('" + PAT + "')\nprint=object()\n",
                       "import logging\nif enabled:\n logging.info('" + PAT + "')\n"):
            with self.subTest(source=source): self.assertFalse(python_contexts(source).complete)
        for source in ("for row in rows:\n print(row)\n", "if enabled:\n print('ordinary')\n",
                       "import logging\nif enabled:\n logging.info('ordinary')\n",
                       "class Result:\n def value(self):\n  return 1\n"):
            with self.subTest(source=source): self.assertTrue(python_contexts(source).complete)

    def test_actual_git_sec001_source_is_masked_and_default_unknown(self):
        source = "# 😀\u2028 physical LF\r\nimport logging\r\ncredential='" + PAT + "'\r\nlogging.error(credential)\r\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "Context Fixture")
            git("config", "core.autocrlf", "false")
            (root / "context.py").write_bytes(source.encode())
            git("add", "context.py")
            git("commit", "-qm", "fixture")
            sha = git("rev-parse", "HEAD")
            adapter = SecurityAdapter(repo_root=root, source_sha=sha)
            record = scan(root, ("context.py",), adapters=(adapter,))
            findings = [finding for finding in record["findings"] if finding["rule_id"] == "SEC001"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["source"]["status"], "VERIFIED")
            self.assertEqual(findings[0]["source"]["before"], "[REDACTED]")
            self.assertEqual(findings[0]["source"]["location"]["region"]["start_line"], 4)
            self.assertEqual(findings[0]["lifecycle_class"], "UNKNOWN")
            self.assertTrue(findings[0]["security_escalation"])
            self.assertNotIn(PAT, json.dumps(record))
            self.assertEqual(git("status", "--porcelain"), "")

    def test_tls_region_overlapping_proven_aws_header_never_leaks_secret(self):
        aws = "Ab7/" * 10
        source = "import requests\nrequests.get('https://example.invalid',verify=False,headers={'aws_secret_access_key':'" + aws + "'})\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            (root / "context.py").write_bytes(source.encode())
            git("add", "context.py")
            git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "core.autocrlf=false", "commit", "-qm", "fixture")
            adapter = SecurityAdapter(repo_root=root, source_sha=git("rev-parse", "HEAD"))
            record = scan(root, ("context.py",), adapters=(adapter,))
            self.assertNotIn(aws, json.dumps(record))
            tls = next(finding for finding in record["findings"] if finding["rule_id"] == "SEC002")
            self.assertEqual(tls["source"]["status"], "VERIFIED")
            self.assertEqual(tls["source"]["before"], "[REDACTED]")


if __name__ == "__main__": unittest.main()
