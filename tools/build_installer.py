"""Build downloadable installer assets without publishing a release."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
import re

if __package__:
    from .package_manifest import inventory
    from .sync_skill_docs import sync
else:
    from package_manifest import inventory
    from sync_skill_docs import sync


def render_script(root, name):
    """Generate all four variants from two templates and one renderer per language."""
    root = Path(root)
    operation, suffix = name.split('.')
    if operation not in {'install', 'update'} or suffix not in {'sh', 'ps1'}:
        raise ValueError('Unknown installer variant')
    text = (root / 'scripts' / ('install.' + suffix)).read_text(encoding='utf-8-sig')
    text = text.replace('@DEVSIFT_OPERATION@', operation)
    helper = 'install_progress.py' if suffix == 'sh' else 'bootstrap_progress.cs'
    marker = '# @DEVSIFT_PROGRESS@'
    if text.count(marker) != 1:
        raise ValueError('Missing bootstrap renderer marker')
    return text.replace(marker, (root / 'tools' / helper).read_text(encoding='utf-8-sig'))


def build(root, output, *, analyzer_bundle=None, analyzer_bundle_digest=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    sync(root, check=True)
    skill_files = inventory(root, 'consumer-skill')
    inventory(root, 'core-wheel')
    if (analyzer_bundle is None) != (analyzer_bundle_digest is None):
        raise ValueError('Analyzer bundle and independently held digest must be supplied together')
    if analyzer_bundle is not None:
        analyzer_bundle = Path(analyzer_bundle)
        if (analyzer_bundle.is_symlink() or analyzer_bundle.is_junction() or not analyzer_bundle.is_file()
                or re.fullmatch(r'devsift-analyzers-(windows|linux|macos)-(x64|arm64)\.zip', analyzer_bundle.name) is None
                or hashlib.sha256(analyzer_bundle.read_bytes()).hexdigest() != analyzer_bundle_digest):
            raise ValueError('Analyzer bundle integrity unavailable')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='devsift-installer-') as tmp:
        stage = Path(tmp)
        subprocess.run([sys.executable, '-I', '-B', '-m', 'pip', 'wheel', '--no-deps',
                        '--no-build-isolation', '--wheel-dir', str(stage / 'wheels'), str(root)], check=True)
        shutil.copy2(root / 'tools/install.py', stage / 'install.py')
        shutil.copy2(root / 'tools/install_progress.py', stage / 'install_progress.py')
        for entry in skill_files:
            target = stage / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / entry.path, target)
        for name in ('.codex-plugin', '.claude-plugin', '.cursor-plugin'):
            (stage / name).mkdir()
            shutil.copy2(root / name / 'plugin.json', stage / name)
        shutil.copy2(root / 'gemini-extension.json', stage)
        shutil.copy2(root / 'plugin.json', stage)
        if analyzer_bundle is not None:
            (stage / 'analyzers').mkdir()
            shutil.copy2(analyzer_bundle, stage / 'analyzers' / analyzer_bundle.name)
            (stage / 'analyzers' / (analyzer_bundle.name + '.sha256')).write_text(
                analyzer_bundle_digest + '  ' + analyzer_bundle.name + '\n', encoding='ascii')
        archive = output / 'devsift-install.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(stage).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / 'devsift-install.zip.sha256').write_text(digest + '  devsift-install.zip\n')
    for name in ('install.ps1', 'update.ps1', 'install.sh', 'update.sh'):
        # Windows checkouts may use CRLF; POSIX shells need LF script assets.
        (output / name).write_text(render_script(root, name),
                                   encoding='utf-8', newline='\n')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--analyzer-bundle', type=Path, help='Embed a verified native companion for offline/platform testing.')
    parser.add_argument('--analyzer-bundle-digest', help='Independently held SHA256 of that companion.')
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1], args.output, analyzer_bundle=args.analyzer_bundle,
                analyzer_bundle_digest=args.analyzer_bundle_digest))
