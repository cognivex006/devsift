from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from devsift.inventory import inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, content=b'print(1)\n'):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def test_sorted_full_inventory_preserves_bytes_and_directories(self):
        for path in ('z.go', 'src/b.ts', 'a.py', 'node_modules/vendor.ts', '.git/config', 'build/a.cs'):
            self.write(path)
        before = {str(p.relative_to(self.root)): None if p.is_dir() else p.read_bytes()
                  for p in self.root.rglob('*')}
        result = inventory(self.root)
        self.assertTrue(result.complete)
        self.assertEqual([t.path for t in result.targets],
                         ['.git', 'a.py', 'build', 'node_modules', 'src/b.ts', 'z.go'])
        self.assertEqual([t.path for t in result.targets if t.status == 'ready'],
                         ['a.py', 'src/b.ts', 'z.go'])
        self.assertEqual(before, {str(p.relative_to(self.root)): None if p.is_dir() else p.read_bytes()
                                  for p in self.root.rglob('*')})

    def test_incremental_is_explicit_deduplicated_and_sorted(self):
        for path in ('b.ts', 'a.py', 'untouched.go'):
            self.write(path)
        result = inventory(self.root, ['b.ts', 'a.py', 'b.ts'])
        self.assertEqual(result.mode, 'incremental')
        self.assertEqual([t.path for t in result.targets], ['a.py', 'b.ts'])
        self.assertEqual(inventory(self.root, []).targets, ())

    def test_bad_paths_fail_before_any_read(self):
        for bad in ('../outside.py', '/etc/passwd', 'C:/src/a.py', 'C:a.py',
                    '..\\a.py', 'dir\\a.py', '//server/share', 'a/../b.py', '', '.', 'a//b.py',
                    'file.py:stream', 'a\x00.py'):
            with self.subTest(path=bad):
                with self.assertRaises(ValueError):
                    inventory(self.root, ['good.py', bad])
        with self.assertRaises(ValueError):
            inventory(self.root, 'single.py')

    def test_portable_special_and_reserved_names_rejected(self):
        for bad in ('a?.py', 'a*.py', 'a|b.py', 'nul.py', 'COM1', 'a./b.py', 'x /b.py', 'a\nb.py'):
            with self.subTest(path=bad):
                with self.assertRaises(ValueError):
                    inventory(self.root, [bad])

    def test_byte_limit_is_incomplete_and_strict(self):
        self.write('a.py', b'12345')
        result = inventory(self.root, max_bytes=4)
        self.assertFalse(result.complete)
        self.assertEqual(result.targets[0].status, 'too_large')
        self.assertIsNone(result.targets[0].content)
        for value in (0, -1, True, '4'):
            with self.assertRaises(ValueError):
                inventory(self.root, max_bytes=value)

    def test_source_content_is_not_exposed_in_debug_repr(self):
        self.write('a.py', b'private-sentinel')
        result = inventory(self.root)
        self.assertEqual(result.targets[0].content, b'private-sentinel')
        self.assertNotIn('private-sentinel', repr(result.targets[0]))
        self.assertNotIn('private-sentinel', repr(result))

    def test_partial_missing_directory_binary_and_unsupported(self):
        self.write('a.py', b'x\x00y')
        self.write('notes.txt', b'notes')
        (self.root / 'folder').mkdir()
        result = inventory(self.root, ['a.py', 'notes.txt', 'missing.ts', 'folder'])
        self.assertFalse(result.complete)
        self.assertEqual({t.path: t.status for t in result.targets},
                         {'a.py': 'binary', 'notes.txt': 'unsupported',
                          'missing.ts': 'missing', 'folder': 'not_file'})

    def test_unreadable_files_and_directories_are_incomplete(self):
        self.write('a.py')
        with patch('devsift.inventory._read_bytes', side_effect=PermissionError):
            result = inventory(self.root)
        self.assertFalse(result.complete)
        self.assertEqual(result.targets[0].status, 'unreadable')
        with patch('devsift.inventory.os.scandir', side_effect=PermissionError):
            result = inventory(self.root)
        self.assertFalse(result.complete)
        self.assertEqual(result.targets[0].status, 'unreadable')

    def test_symlinks_are_never_followed(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / 'secret.py').write_bytes(b'secret')
            try:
                (self.root / 'link').symlink_to(outside, target_is_directory=True)
            except OSError as error:
                self.skipTest(f'Host symlink creation unavailable: {error}')
            for candidates in (None, ['link/secret.py'], ['link']):
                result = inventory(self.root, candidates)
                self.assertFalse(result.complete)
                self.assertEqual(result.targets[0].status, 'unsafe')
                self.assertIsNone(result.targets[0].content)

    def test_excluded_incremental_path_never_read(self):
        self.write('.venv/lib/example.py')
        with patch('devsift.inventory._read_bytes', side_effect=AssertionError('must not read')):
            result = inventory(self.root, ['.venv/lib/example.py'])
        self.assertEqual(result.targets[0].status, 'excluded')


class WorktreeExclusion(unittest.TestCase):
    def test_job_worktree_container_is_never_recursively_scanned(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'worktrees' / 'job').mkdir(parents=True)
            (root / 'worktrees' / 'job' / 'source.py').write_bytes(b'private job bytes')
            result = inventory(root)
            self.assertEqual([(target.path, target.status) for target in result.targets],
                             [('worktrees', 'excluded')])
            selected = inventory(root, ['worktrees/job/source.py'])
            self.assertEqual(selected.targets[0].status, 'excluded')
            self.assertIsNone(selected.targets[0].content)


if __name__ == '__main__':
    unittest.main()
