"""Full runs do not discard security candidates at legacy inline budgets."""
import unittest

from devsift.inventory import SourceTarget
from devsift.security_adapter import SecurityAdapter
from devsift.security_context import python_contexts


class CompleteSecurityTests(unittest.TestCase):
    def test_large_source_and_over_thousand_credentials_are_all_analyzed(self):
        source = '#' + 'x' * 2_100_000 + '\n' + '\n'.join(
            f'key{index} = "' + 'gh' + 'p_' + f'{index:036d}' + '"'
            for index in range(1001)) + '\n'
        target = SourceTarget('source.py', 'ready', 'python', source.encode(), '')
        bounded = SecurityAdapter().analyze(target)
        self.assertFalse(bounded.complete)
        complete = SecurityAdapter(complete_run=True).analyze(target)
        self.assertTrue(complete.complete)
        self.assertEqual(len(complete.findings), 1001)
        self.assertEqual(len({finding.case_id for finding in complete.findings}), 1001)
        self.assertTrue(all(finding.rule_id == 'HC002' for finding in complete.findings))

    def test_security_contexts_keep_all_over_thousand_diagnostics_in_full_mode(self):
        source = 'import ssl\n' + 'context = ssl._create_unverified_context()\n' * 1001
        bounded = python_contexts(source)
        self.assertFalse(bounded.complete)
        self.assertEqual(len(bounded.diagnostics), 1000)
        complete = python_contexts(source, complete_run=True)
        self.assertTrue(complete.complete)
        self.assertEqual(len(complete.diagnostics), 1001)


if __name__ == '__main__':
    unittest.main()
