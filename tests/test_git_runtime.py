import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devsift.git_runtime import GitRuntimeError, git_executable


class GitRuntimeTests(unittest.TestCase):
    def test_actual_host_git_is_absolute_and_outside_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            executable=Path(git_executable(root))
            self.assertTrue(executable.is_absolute())
            self.assertFalse(executable.is_relative_to(root))
            self.assertTrue(executable.is_file())

    def test_target_path_entry_is_ignored_without_executing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);name='git.exe' if os.name=='nt' else 'git'
            fake=root/name;fake.write_bytes(b'not a trusted host executable');fake.chmod(0o755)
            with patch.dict(os.environ,PATH=str(root)+os.pathsep+os.environ.get('PATH','')):
                executable=Path(git_executable(root))
            self.assertFalse(executable.is_relative_to(root))
            self.assertEqual(fake.read_bytes(),b'not a trusted host executable')

    def test_missing_relative_and_target_only_path_fail_with_constant_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);fake=root/('git.exe' if os.name=='nt' else 'git')
            fake.write_bytes(b'privateFakeExecutableValue');fake.chmod(0o755)
            for path in ['', '.', str(root), '.'+os.pathsep+str(root)]:
                with self.subTest(path=path),patch.dict(os.environ,PATH=path):
                    with self.assertRaisesRegex(GitRuntimeError,'^Trusted host Git is unavailable$') as error:
                        git_executable(root)
                    self.assertNotIn('privateFakeExecutableValue',str(error.exception))

    def test_absolute_link_to_project_is_not_a_host_provider(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root=Path(directory);fake=root/('git.exe' if os.name=='nt' else 'git')
            fake.write_bytes(b'project executable');fake.chmod(0o755)
            alias=Path(outside)/'alias'
            try:alias.symlink_to(root,target_is_directory=True)
            except OSError as error:self.skipTest(str(error))
            with patch.dict(os.environ,PATH=str(alias)):
                with self.assertRaises(GitRuntimeError):git_executable(root)

    def test_scanner_snapshot_uses_host_git_when_target_path_is_present(self):
        from test_case_cli import CaseCliTests
        from devsift.evidence import Region,verify_source
        from devsift.scanner import _snapshot_matches_commit
        fixture=CaseCliTests();fixture.setUp()
        try:
            source=verify_source(fixture.project,'fixture/repo',fixture.sha,'client.ts',
                                 Region(1,1,1,len(fixture.code.rstrip())+1))
            fake=fixture.project/('git.exe' if os.name=='nt' else 'git')
            fake.write_bytes(b'untrusted target executable');fake.chmod(0o755)
            before=fixture.snapshot()
            with patch.dict(os.environ,PATH=str(fixture.project)+os.pathsep+os.environ.get('PATH','')):
                self.assertTrue(_snapshot_matches_commit(fixture.project,source,fixture.code.encode()))
            self.assertEqual(fixture.snapshot(),before)
        finally:fixture.doCleanups()


if __name__=='__main__':unittest.main()
