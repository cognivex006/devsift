"""Generated Windows bootstraps in native terminals, against a local HTTP fixture."""
import os
import unittest
from bootstrap_support import BootstrapCases


@unittest.skipUnless(os.name == 'nt', 'Windows native terminal required')
class WindowsBootstrapTests(BootstrapCases, unittest.TestCase):
    suffix = 'ps1'

    def test_broken_first_python_candidate_falls_back(self):
        self.run_bootstrap('update', broken_first=True)
