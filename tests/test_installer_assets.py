"""Generated asset boundaries and marketplace discoverability."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
from tools import build_installer

ROOT = Path(__file__).resolve().parents[1]


class InstallerAssetTests(unittest.TestCase):
    def test_six_generated_assets_bind_sources_and_exclude_maintainer_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            def wheel(argv, **kwargs):
                destination = Path(argv[argv.index('--wheel-dir') + 1])
                destination.mkdir()
                (destination / 'devsift-0.1.12-py3-none-any.whl').write_bytes(b'offline wheel fixture')
            with patch.object(build_installer, 'subprocess', SimpleNamespace(run=wheel)):
                archive = build_installer.build(ROOT, tmp)
            root = Path(tmp)
            self.assertEqual({p.name for p in root.iterdir()}, {
                'install.ps1', 'update.ps1', 'install.sh', 'update.sh',
                'devsift-install.zip', 'devsift-install.zip.sha256'})
            digest = (root / 'devsift-install.zip.sha256').read_text().split()[0]
            self.assertEqual(digest, hashlib.sha256(archive.read_bytes()).hexdigest())
            with zipfile.ZipFile(archive) as z:
                names = set(z.namelist())
                self.assertIn('plugin.json', names)
                self.assertIn('install_progress.py', names)
                self.assertIn('skills/devsift/references/REPORT-TEMPLATE.md', names)
                self.assertNotIn('AGENTS.md', names)
                self.assertFalse(any('TERMINAL-UX' in n or '/development/' in n for n in names))
                self.assertEqual(z.read('install_progress.py'), (ROOT / 'tools/install_progress.py').read_bytes())
            for operation in ('install', 'update'):
                for suffix in ('ps1', 'sh'):
                    name = operation + '.' + suffix
                    script = (root / name).read_text(encoding='utf-8')
                    self.assertEqual(script, build_installer.render_script(ROOT, name))
                    self.assertNotIn('@DEVSIFT_', script)
                    self.assertNotIn('\r', (root / name).read_bytes().decode())
                    if suffix == 'sh':
                        code = script.split("<<'PY'\n", 1)[1].rsplit('\nPY', 1)[0]
                        compile(code, name, 'exec')
                        self.assertIn("operation='" + operation + "'", code)
                    else:
                        self.assertNotIn('Write-Progress', script)
                        self.assertIn("$operation = '" + operation + "'", script)

    def test_catalogs_resolve_the_consumer_plugin_and_versions_agree(self):
        manifest = json.loads((ROOT / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'], 'devsift')
        self.assertNotIn('hooks', manifest)
        for catalog in ('.claude-plugin/marketplace.json', '.github/plugin/marketplace.json',
                        '.cursor-plugin/marketplace.json'):
            data = json.loads((ROOT / catalog).read_text())
            self.assertEqual(data['name'], 'devsift')
            plugin = data['plugins'][0]
            self.assertEqual(plugin['name'], 'devsift')
            location = ROOT / plugin['source']
            self.assertTrue((location / 'skills/devsift/SKILL.md').is_file())
        data = json.loads((ROOT / '.agents/plugins/marketplace.json').read_text())
        self.assertTrue((ROOT / data['plugins'][0]['source']['path'] / '.codex-plugin/plugin.json').is_file())
        for path in ('.codex-plugin/plugin.json', '.claude-plugin/plugin.json', '.cursor-plugin/plugin.json',
                     'gemini-extension.json'):
            self.assertEqual(json.loads((ROOT / path).read_text())['version'], manifest['version'])
