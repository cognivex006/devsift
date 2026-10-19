"""Portable companion safety and opt-in actual bundled-runtime execution."""
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from devsift.native_host import ToolDefinition, file_digest
from devsift.native_manifest import ConfiguredTool, load_manifest
from devsift.process_runner import ProcessSpec
from tools import build_analyzer_bundle as builder


class AnalyzerBundleTests(unittest.TestCase):
    def test_template_rebases_only_payload_paths_and_preserves_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            executable = stage / 'frontend/node.exe'; executable.parent.mkdir()
            executable.write_bytes(b'owned executable fixture')
            script = executable.parent / 'analyze.cjs'; script.write_bytes(b'owned script fixture')
            tool = ToolDefinition('fixture', '1', ('typescript',), ProcessSpec(str(executable), (str(script),)),
                                  file_digest(executable), ((str(script), file_digest(script)),))
            template = builder._template([ConfiguredTool(tool)], stage, 'windows-x64')
            definition = template['tools'][0]['definition']
            self.assertEqual(definition['process']['executable'], '@ROOT@/frontend/node.exe')
            self.assertEqual(definition['process']['argv'], ['@ROOT@/frontend/analyze.cjs'])
            self.assertEqual(definition['executable_digest'], tool.executable_digest)
            self.assertEqual(definition['artifacts'], [['@ROOT@/frontend/analyze.cjs', file_digest(script)]])
            self.assertEqual(set(template), {'schema_version', 'platform', 'tools'})
            outside = copy.deepcopy(tool)
            from dataclasses import replace
            outside = replace(outside, process=ProcessSpec(str(Path(sys.executable).resolve())))
            with self.assertRaises(ValueError):
                builder._template([ConfiguredTool(outside)], stage, 'windows-x64')

    def test_copy_preserves_real_files_and_excludes_npm_command_wrappers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'package').mkdir(); (source / 'package/LICENSE').write_bytes(b'actual license fixture')
            (source / '.bin').mkdir(); (source / '.bin/wrapper').write_bytes(b'must not ship')
            builder.copy_tree(source, root / 'payload', skip_bins=True)
            self.assertEqual((root / 'payload/package/LICENSE').read_bytes(), b'actual license fixture')
            self.assertFalse((root / 'payload/.bin').exists())
            with self.assertRaises(FileExistsError):
                builder.copy_file(source / 'package/LICENSE', root / 'payload/package/LICENSE')

    @unittest.skipIf(os.name == 'nt', 'Windows symlink creation requires separate privilege')
    def test_copy_refuses_symlink_files_and_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); outside = root / 'outside'; outside.mkdir()
            (outside / 'private').write_bytes(b'not copied')
            for directory in (False, True):
                source = root / ('source-dir' if directory else 'source-file'); source.mkdir()
                (source / 'link').symlink_to(outside if directory else outside / 'private', target_is_directory=directory)
                with self.assertRaises(ValueError):
                    builder.copy_tree(source, root / ('payload-dir' if directory else 'payload-file'))

    def test_foreign_platform_is_refused_before_building(self):
        foreign = next(p for p in builder.PLATFORMS if p != builder.current_platform())
        with tempfile.TemporaryDirectory() as temporary, patch.object(builder, '_run') as run:
            with self.assertRaises(ValueError):
                builder.build(Path(temporary), platform=foreign)
            run.assert_not_called()


@unittest.skipUnless(os.environ.get('DEVSIFT_TEST_ANALYZER_BUNDLE'), 'requires an explicitly built companion archive')
class ActualAnalyzerBundleTests(unittest.TestCase):
    def test_archive_inventory_and_all_four_runtimes_work_without_sdk_path(self):
        archive_path = Path(os.environ['DEVSIFT_TEST_ANALYZER_BUNDLE']).resolve(strict=True)
        expected = os.environ['DEVSIFT_TEST_ANALYZER_BUNDLE_SHA256']
        self.assertEqual(file_digest(archive_path), expected)
        with tempfile.TemporaryDirectory(prefix='devsift-companion-test-') as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                self.assertEqual(len(members), len({m.filename.casefold() for m in members}))
                for member in members:
                    path = PurePosixPath(member.filename)
                    self.assertFalse(path.is_absolute())
                    self.assertFalse(any(part in ('', '.', '..') for part in path.parts))
                    self.assertNotIn('\\', member.filename)
                    self.assertFalse(stat.S_ISLNK(member.external_attr >> 16))
                    self.assertFalse(member.filename.lower().endswith('.pdb'))
                inventory = json.loads(archive.read('inventory.json'))
                records = {item['path']: item for item in inventory['files']}
                self.assertEqual(set(records) | {'inventory.json'}, {m.filename for m in members})
                for member in members:
                    body = archive.read(member)
                    if member.filename != 'inventory.json':
                        self.assertEqual(len(body), records[member.filename]['size'])
                        self.assertEqual(hashlib.sha256(body).hexdigest(), records[member.filename]['sha256'])
                    destination = root / member.filename
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(body)
                    destination.chmod((member.external_attr >> 16) & 0o777)
            template = json.loads((root / 'manifest-template.json').read_bytes())
            self.assertEqual(template.pop('platform'), builder.current_platform())
            for entry in template['tools']:
                definition = entry['definition']
                def rebase(value):
                    self.assertTrue(value.startswith('@ROOT@/'))
                    return str(root / value.removeprefix('@ROOT@/'))
                definition['process']['executable'] = rebase(definition['process']['executable'])
                definition['process']['argv'] = [rebase(value) for value in definition['process']['argv']]
                definition['artifacts'] = [[rebase(path), digest] for path, digest in definition['artifacts']]
            raw = json.dumps(template).encode(); manifest = root / 'manifest.json'; manifest.write_bytes(raw)
            entries = load_manifest(str(manifest), hashlib.sha256(raw).hexdigest())
            with patch.dict(os.environ, {'PATH': '', 'DOTNET_ROOT': str(root / 'absent-sdk'), 'NODE_PATH': ''}):
                results = builder.smoke(entries)
            self.assertEqual(len(results), 4)
            self.assertTrue(all(item['diagnostics'] == 1 for item in results))
            self.assertTrue((root / 'licenses/Node-LICENSE.txt').is_file())
            self.assertTrue((root / 'licenses/dotnet-LICENSE.txt').is_file())
            self.assertTrue((root / 'licenses/Go-LICENSE.txt').is_file())
            dependency_inventory = json.loads((root / 'dependency-inventory.json').read_bytes())
            self.assertEqual(dependency_inventory['project_license'], 'NOASSERTION')
            self.assertFalse(dependency_inventory['redistribution_approved'])


if __name__ == '__main__':
    unittest.main()
