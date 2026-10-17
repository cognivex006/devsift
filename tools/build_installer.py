"""Build downloadable installer assets without publishing a release."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

if __package__:
    from .package_manifest import inventory
    from .sync_skill_docs import sync
else:
    from package_manifest import inventory
    from sync_skill_docs import sync


def build(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    sync(root, check=True)
    skill_files = inventory(root, 'consumer-skill')
    inventory(root, 'core-wheel')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='devsift-installer-') as tmp:
        stage = Path(tmp)
        subprocess.run([sys.executable, '-I', '-B', '-m', 'pip', 'wheel', '--no-deps',
                        '--no-build-isolation', '--wheel-dir', str(stage / 'wheels'), str(root)], check=True)
        shutil.copy2(root / 'tools/install.py', stage / 'install.py')
        for entry in skill_files:
            target = stage / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / entry.path, target)
        for name in ('.codex-plugin', '.claude-plugin', '.cursor-plugin'):
            (stage / name).mkdir()
            shutil.copy2(root / name / 'plugin.json', stage / name)
        shutil.copy2(root / 'gemini-extension.json', stage)
        archive = output / 'devsift-install.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(stage).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'devsift-install.zip.sha256').write_text(digest + '  devsift-install.zip\n')
    for name in ('install.ps1', 'update.ps1', 'install.sh', 'update.sh'):
        shutil.copy2(root / 'scripts' / name, output / name)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.output))
