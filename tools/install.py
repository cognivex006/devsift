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
import platform
import re
import urllib.request

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


def _platform():
    system = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'macos'}.get(platform.system())
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine().lower())
    if not system or not arch:
        raise RuntimeError('No analyzer package for this platform. Existing installation was preserved.')
    return system + '-' + arch


def _receive(url, destination, transfer, label, limit):
    request = urllib.request.Request(url, headers={'User-Agent': 'DevSift installer'})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open('xb') as output:
        total = int(response.headers.get('Content-Length') or 0)
        if total < 0:
            raise RuntimeError('Invalid analyzer download length.')
        if total > limit:
            raise RuntimeError('Analyzer release asset exceeds the setup size limit.')
        received = 0
        transfer(0, total or None, label)
        while block := response.read(65536):
            received += len(block)
            if received > limit:
                raise RuntimeError('Analyzer release asset exceeds the setup size limit.')
            output.write(block)
            transfer(received, total or None, label)
        if total and received != total:
            raise RuntimeError('Analyzer download ended before the declared bytes arrived.')


def _analyzers(python, bundle, home, version, report, transfer):
    name = 'devsift-analyzers-' + _platform() + '.zip'
    report(67, 'Preparing code analyzers')
    with tempfile.TemporaryDirectory(prefix='devsift-analyzer-download-') as temporary:
        temporary = Path(temporary).resolve()
        local = bundle / 'analyzers' / name
        archive = local if local.is_file() else temporary / name
        checksum = local.with_suffix('.zip.sha256')
        if local.is_file():
            if local.is_symlink() or local.is_junction() or checksum.is_symlink() or checksum.is_junction():
                raise RuntimeError('Unsafe embedded analyzer package.')
            raw = checksum.read_text(encoding='ascii')
        else:
            if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) is None:
                raise RuntimeError('Invalid release version for analyzer setup.')
            base = 'https://github.com/orchex006/devsift/releases/download/v' + version + '/'
            report(67, 'Downloading platform analyzers')
            _receive(base + name, archive, transfer, name, 512_000_000)
            checksum = temporary / (name + '.sha256')
            _receive(base + checksum.name, checksum, transfer, checksum.name, 4096)
            raw = checksum.read_text(encoding='ascii')
        match = re.fullmatch(r'([a-f0-9]{64})  ' + re.escape(name) + r'\s*', raw)
        if not match:
            raise RuntimeError('Invalid analyzer release checksum.')
        report(68, 'Extracting and checking code analyzers')
        run = subprocess.run([str(python), '-I', '-B', '-m', 'devsift', 'setup',
            '--analyzer-bundle', str(archive), '--bundle-digest', match[1], '--home', str(home)],
            cwd=python.parent, check=False, capture_output=True, text=True)
        try:
            state = json.loads(run.stdout)
            if type(state) is not dict or type(state.get('data')) is not dict:
                raise ValueError('Invalid setup result')
            if run.returncode:
                probes = state.get('data', {}).get('probes', [])
                if (type(probes) is not list or any(type(item) is not dict or
                        type(item.get('tool_id')) is not str or type(item.get('reason')) is not str
                        for item in probes)):
                    raise ValueError('Invalid setup result')
                failed = ', '.join(item['tool_id'] + ': ' + item['reason']
                                   for item in probes if item.get('available') is False)
                raise RuntimeError('Code analyzer setup failed' + (': ' + failed if failed else '')
                                   + '. Existing CLI launcher was preserved.')
            ready = state['data']['analysis_ready']
            tools = set(state['data']['registered_tools'])
        except (ValueError, KeyError, TypeError):
            raise RuntimeError('Analyzer setup returned an invalid readiness result.') from None
        if ready is not True or tools != {'devsift-go', 'devsift-roslyn', 'devsift-sql', 'devsift-typescript'}:
            raise RuntimeError('Code analyzers did not pass readiness checks. Existing launcher was preserved.')
        return state['data']


def install(bundle, home, bin_dir, hosts, *, progress=None, transfer=None, require_analyzers=False):
    report = progress if progress is not None else lambda percent, stage: None
    transfer = transfer if transfer is not None else lambda received, total, stage: None
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
        analyzers = (_analyzers(python, bundle, home, wheels[0].name.split('-')[1], report, transfer)
                     if require_analyzers else {'analysis_ready': False})
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
             'skills': list(map(str, destinations)), 'plugin': str(plugin), **analyzers}
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
    parser.add_argument('--core-only', action='store_true', help='Install only CLI/skills; does not prepare code analyzers.')
    args = parser.parse_args()
    with Progress(args.progress) as progress:
        try:
            state = install(args.bundle, args.home, args.bin_dir or args.home / '.local/bin', args.hosts,
                            progress=progress.update, transfer=progress.transfer, require_analyzers=not args.core_only)
            if args.core_only and args.progress != 'json':
                progress.finish(message='DevSift CLI/skills installed. Code analyzers were not configured (--core-only).')
            else:
                progress.finish(state=state)
            return 0
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            if isinstance(error, subprocess.CalledProcessError):
                error = RuntimeError(f'CLI installation check failed (exit {error.returncode}).')
            elif isinstance(error, ValueError):
                error = RuntimeError('Invalid analyzer download or installation metadata.')
            progress.fail(error)
            return 1
        except KeyboardInterrupt:
            progress.fail('Cancelled.')
            return 130


if __name__ == '__main__':
    raise SystemExit(main())
