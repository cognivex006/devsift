import os
from pathlib import Path
import tempfile
import unittest

from devsift.command_inputs import CommandInputError, load_json_input


class CommandInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def write(self,content):
        p=self.root/'input.json';p.write_bytes(content);return p

    def test_explicit_input_is_fresh_bounded_and_read_only(self):
        path=self.write(b'{"one":{"two":3}}');before=path.read_bytes()
        value=load_json_input(path);value['one']['two']=4
        self.assertEqual(load_json_input(path),{'one':{'two':3}})
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(list(self.root.iterdir()),[path])

    def test_invalid_duplicate_nonfinite_deep_and_unicode_are_constant_safe(self):
        for raw in [b'{"one":1,"one":2}',b'{"x":NaN}',b'{"x":Infinity}',b'privateInputValue',b'\xff',b'['*2000+b']'*2000]:
            with self.subTest(raw=raw[:20]):
                path=self.write(raw)
                with self.assertRaisesRegex(CommandInputError,'^Invalid or unavailable command input$') as error:
                    load_json_input(path)
                self.assertNotIn('privateInputValue',str(error.exception))
                self.assertEqual(path.read_bytes(),raw)

    def test_missing_directory_and_oversize_never_create_or_remove_files(self):
        with self.assertRaises(CommandInputError):load_json_input(self.root/'privateMissing.json')
        with self.assertRaises(CommandInputError):load_json_input(self.root)
        path=self.write(b' '*4097)
        with self.assertRaises(CommandInputError):load_json_input(path,maximum_bytes=4096)
        self.assertEqual(path.stat().st_size,4097)
        self.assertFalse((self.root/'privateMissing.json').exists())

    def test_symlink_input_and_parent_are_refused(self):
        target=self.write(b'{"private":"untrustedValue"}')
        link=self.root/'input-link.json'
        try:link.symlink_to(target)
        except OSError as error:self.skipTest(str(error))
        with self.assertRaises(CommandInputError):load_json_input(link)
        with tempfile.TemporaryDirectory() as directory:
            alias=Path(directory)/'alias'
            alias.symlink_to(self.root,target_is_directory=True)
            with self.assertRaises(CommandInputError):load_json_input(alias/'input.json')
        self.assertEqual(target.read_bytes(),b'{"private":"untrustedValue"}')


if __name__=='__main__':unittest.main()
