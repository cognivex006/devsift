"""Generated Posix bootstraps in native terminals, against a local HTTP fixture."""
import os
import unittest
from bootstrap_support import BootstrapCases


@unittest.skipUnless(os.name == 'posix', 'Posix native terminal required')
class PosixBootstrapTests(BootstrapCases, unittest.TestCase):
    suffix = 'sh'
