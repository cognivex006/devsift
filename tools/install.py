"""Install a reviewed release bundle into a private environment and user skill paths."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import venv

if __package__:
    from .install_progress import Progress
else:
    # Explicit trusted bootstrap directory, never the consumer working directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from install_progress import Progress


HOST_PATHS = {
    'codex': ('.agents/skills',),
    'claude': ('.claude/skills',),
    'gemini': ('.gemini/skills',),
    'antigravity': ('.gemini/config/skills', '.gemini/antigravity-cli/skills'),
    'cursor': ('.cursor/skills',),
    # Copilot officially discovers .agents/skills too; share Codex's copy.
    'copilot': ('.agents/skills',),
}


def replace_managed_tree(source, destination):
    """Replace the complete owned directory so obsolete instructions disappear."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.devsift-stage-', dir=destination.parent) as tmp:
        staged, backup = Path(tmp) / 'new', Path(tmp) / 'previous'
        shutil.copytree(source, staged)
        (staged / '.devsift-managed').write_text('Managed by the DevSift installer.\n')
        if destination.exists():
            destination.replace(backup)
        try:
            staged.replace(destination)
        except BaseException:
            if backup.exists():
                backup.replace(destination)
            raise


def install(bundle, home, bin_dir, hosts, *, progress=None):
    report = progress if progress is not None else lambda percent, stage: None
    report(0, 'Checking installation paths')
    if sys.version_info < (3, 12):
        raise RuntimeError('DevSift requires Python 3.12 or later.')
    bundle, home, bin_dir = map(lambda p: Path(p).resolve(), (bundle, home, bin_dir))
    wheels = list((bundle / 'wheels').glob('devsift-*.whl'))
    if len(wheels) != 1 or not (bundle / 'skills/devsift/SKILL.md').is_file():
        raise RuntimeError('Expected one DevSift wheel and its consumer skill.')
    destinations = list(dict.fromkeys(home / path / 'devsift' for host in hosts for path in HOST_PATHS[host]))
    plugin = home / '.local/share/devsift/plugin'
    for dest in [*destinations, plugin]:
        if dest.is_symlink() or dest.is_junction() or (dest.exists() and not (dest / '.devsift-managed').is_file()):
            raise RuntimeError(f'Existing unmanaged skill: {dest}. Move it aside before installing.')
    # Keep the working environment until pip and the new CLI help both succeed.
    version = home / '.local/share/devsift/versions' / uuid.uuid4().hex
    report(10, f'Creating private Python {sys.version_info.major}.{sys.version_info.minor} environment')
    python = version / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    try:
        venv.create(version, with_pip=True)
        report(45, 'Installing CLI from verified local wheel')
        subprocess.run([str(python), '-I', '-B', '-m', 'pip', 'install', '--no-index',
                        '--no-deps', str(wheels[0])], check=True, cwd=version, capture_output=True, text=True)
        report(65, 'Checking CLI startup')
        subprocess.run([str(python), '-I', '-B', '-m', 'devsift', '--help'],
                       check=True, capture_output=True, cwd=version)
    except BaseException:
        if version.exists():
            shutil.rmtree(version)
        raise
    bin_dir.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        launcher = bin_dir / 'devsift.cmd'
        content = f'@echo off\r\n"{python}" -I -B -m devsift %*\r\n'
    else:
        import shlex
        launcher = bin_dir / 'devsift'
        content = '#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' -I -B -m devsift "$@"\n'
    pending = launcher.with_suffix('.new')
    pending.write_text(content, encoding='utf-8', newline='')
    pending.chmod(0o755)
    for index, dest in enumerate(destinations):
        report(70 + index * 12 // len(destinations), f'Installing skill: {dest.parent.relative_to(home)} ({index + 1}/{len(destinations)})')
        replace_managed_tree(bundle / 'skills/devsift', dest)
    report(84, 'Preparing plugin bundle')
    with tempfile.TemporaryDirectory(prefix='devsift-plugin-') as tmp:
        staged_plugin = Path(tmp) / 'plugin'
        shutil.copytree(bundle / 'skills', staged_plugin / 'skills')
        for name in ('.codex-plugin', '.claude-plugin', '.cursor-plugin'):
            shutil.copytree(bundle / name, staged_plugin / name)
        shutil.copy2(bundle / 'gemini-extension.json', staged_plugin)
        shutil.copy2(bundle / 'plugin.json', staged_plugin)
        replace_managed_tree(staged_plugin, plugin)
    report(92, 'Activating verified CLI launcher')
    pending.replace(launcher)
    state = {'version': wheels[0].name.split('-')[1], 'python': str(python), 'launcher': str(launcher), 'hosts': hosts,
             'skills': list(map(str, destinations)), 'plugin': str(plugin)}
    (home / '.local/share/devsift/installation.json').write_text(json.dumps(state, indent=2))
    report(100, 'CLI and skills installed')
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--bin-dir', type=Path)
    parser.add_argument('--hosts', nargs='+', choices=HOST_PATHS, default=list(HOST_PATHS))
    parser.add_argument('--progress', choices=('console', 'json', 'none'), default='console')
    args = parser.parse_args()
    with Progress(args.progress) as progress:
        try:
            state = install(args.bundle, args.home, args.bin_dir or args.home / '.local/bin', args.hosts,
                            progress=progress.update)
            progress.finish(state=state)
            return 0
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            if isinstance(error, subprocess.CalledProcessError):
                error = RuntimeError(f'CLI installation check failed (exit {error.returncode}).')
            progress.fail(error)
            return 1
        except KeyboardInterrupt:
            progress.fail('Cancelled.')
            return 130


if __name__ == '__main__':
    raise SystemExit(main())
