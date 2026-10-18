"""Generated Windows bootstraps in native terminals, against a local HTTP fixture."""
import os
import unittest
from bootstrap_support import BootstrapCases


@unittest.skipUnless(os.name == 'nt', 'Windows native terminal required')
class WindowsBootstrapTests(BootstrapCases, unittest.TestCase):
    suffix = 'ps1'
