"""Author platform companions from DevSift-owned helpers; never build target code.

The output contains runtimes, not SDKs. Publishing/licensing approval is separate.
The installer rebases only @ROOT@ paths after independently verifying archive SHA256.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform as host_platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from devsift.native_host import ToolDefinition, analyze_snapshot, file_digest, probe_tool
from devsift.native_manifest import ConfiguredTool, manifest_bytes
from devsift.inventory import SourceTarget
from devsift.process_runner import ProcessSpec
from tools.install_progress import Progress

PLATFORMS = tuple(system + '-' + arch for system in ('windows', 'linux', 'macos') for arch in ('x64', 'arm64'))


def current_platform():
    system = {'Windows': 'windows', 'Linux': 'linux', 'Darwin': 'macos'}.get(host_platform.system())
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(host_platform.machine().lower())
    if not system or not arch:
        raise ValueError('Unsupported analyzer companion platform')
    return system + '-' + arch


def _plain(path, directory=False):
    info = Path(path).lstat()
    if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError('Analyzer input must be a physical regular file/directory')
    return info


def copy_file(source, destination):
    source, destination = Path(source), Path(destination)
    before = _plain(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    descriptor = os.open(source, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('Analyzer input changed during copy')
        with os.fdopen(descriptor, 'rb', closefd=False) as incoming, destination.open('xb') as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
    finally:
        os.close(descriptor)
    after = _plain(source)
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or file_digest(source) != file_digest(destination)):
        raise ValueError('Analyzer input changed during copy')
    destination.chmod(stat.S_IMODE(before.st_mode))


def copy_tree(source, destination, *, skip_bins=False):
    """Copy physical package files; exclude npm command-link wrappers entirely."""
    source, destination = Path(source), Path(destination)
    _plain(source, directory=True)
    destination.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.iterdir(), key=lambda p: p.name):
        if skip_bins and entry.name == '.bin':
            continue
        info = entry.lstat()
        if stat.S_ISDIR(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 1024:
            copy_tree(entry, destination / entry.name, skip_bins=skip_bins)
        else:
            copy_file(entry, destination / entry.name)


def _run(command, directory, progress, stage, log, *, environment=None):
    progress.update(20, stage)
    with log.open('ab') as stream:
        stream.write(('\nCOMMAND ' + json.dumps(list(map(str, command))) + '\n').encode())
        completed = subprocess.run(list(map(str, command)), cwd=directory,
                                   env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=1200)
    if completed.returncode:
        raise RuntimeError('Owned analyzer build command failed; inspect build log')


def _capture(command, directory):
    return subprocess.run(list(map(str, command)), cwd=directory, check=True,
                          capture_output=True, text=True, timeout=30).stdout.strip()


def _runtime_license(node):
    for candidate in (node.parent / 'LICENSE', node.parent / 'LICENSE.txt', node.parent.parent / 'LICENSE'):
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise ValueError('Node runtime LICENSE is required; use an official Node distribution')


def _template(entries, stage, platform):
    data = json.loads(manifest_bytes(tuple(entries)))
    data['platform'] = platform
    def relative(value):
        path = Path(value)
        if not path.is_absolute() or not path.is_relative_to(stage):
            raise ValueError('Companion manifest path must stay inside payload')
        return '@ROOT@/' + path.relative_to(stage).as_posix()
    for entry in data['tools']:
        definition = entry['definition']
        definition['process']['executable'] = relative(definition['process']['executable'])
        definition['process']['argv'] = [relative(value) for value in definition['process']['argv']]
        definition['artifacts'] = [[relative(path), digest] for path, digest in definition['artifacts']]
    return data


def _json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + '\n', encoding='utf-8', newline='\n')


def _tools(stage, suffix):
    def make(tool_id, version, language, folder, helper, names, engines, dialect=None):
        directory = stage / folder
        executable = directory / (helper + suffix)
        artifacts = tuple((str(directory / name), file_digest(directory / name)) for name in names)
        tool = ToolDefinition(tool_id, version, (language,), ProcessSpec(str(executable), timeout_seconds=30),
                              file_digest(executable), artifacts, engines)
        return ConfiguredTool(tool, dialect)
    entries = [
        make('devsift-roslyn', '1.0.0', 'csharp', 'dotnet', 'DevSift.Roslyn',
             ('DevSift.Roslyn.dll', 'DevSift.Roslyn.deps.json', 'DevSift.Roslyn.runtimeconfig.json',
              'Microsoft.CodeAnalysis.dll', 'Microsoft.CodeAnalysis.CSharp.dll'), (('roslyn', '4.13.0.0'),)),
        make('devsift-sql', '1.1.0', 'sql', 'sql', 'DevSift.Sql',
             ('DevSift.Sql.dll', 'DevSift.Sql.deps.json', 'DevSift.Sql.runtimeconfig.json',
              'Microsoft.SqlServer.TransactSql.ScriptDom.dll'), (('scriptdom', '161.8901.0'),), 'tsql160'),
    ]
    executable = stage / 'go' / ('devsift-go' + suffix)
    entries.append(ConfiguredTool(ToolDefinition('devsift-go', '1.0.0', ('go',), ProcessSpec(str(executable)),
        file_digest(executable), ((str(executable), file_digest(executable)),), (('go', 'go1.21.3'),))))
    directory = stage / 'frontend'; executable = directory / ('node' + suffix)
    entries.append(ConfiguredTool(ToolDefinition('devsift-typescript', '1.2.0', ('typescript', 'javascript'),
        ProcessSpec(str(executable), (str(directory / 'analyze.cjs'),), timeout_seconds=30), file_digest(executable),
        tuple((str(directory / name), file_digest(directory / name)) for name in ('analyze.cjs', 'package.json', 'package-lock.json')),
        (('eslint', '10.12.0'), ('parser', '8.71.2'), ('typescript', '6.0.3')))))
    return entries


def smoke(entries):
    fixtures = {'devsift-roslyn': ('a.cs', 'csharp', 'using System; class C { static void Main(){ Console.WriteLine(1); } }'),
                'devsift-sql': ('a.sql', 'sql', "DECLARE @q nvarchar(max)=N'SELECT * FROM dbo.T WHERE id=' + @input; EXEC(@q);"),
                'devsift-go': ('a.go', 'go', 'package main\nimport "fmt"\nfunc main(){fmt.Println(1)}'),
                'devsift-typescript': ('a.js', 'javascript', 'try {} catch {}')}
    results = []
    for entry in entries:
        probe = probe_tool(entry.tool)
        if not probe.available or 'files' not in probe.transports:
            raise RuntimeError('Bundled runtime probe failed')
        path, language, source = fixtures[entry.tool.tool_id]
        report = analyze_snapshot(entry.tool, SourceTarget(path, 'ready', language, source.encode(), 'owned-fixture'), dialect=entry.dialect)
        if not report.complete or len(report.diagnostics) != 1:
            raise RuntimeError('Bundled runtime AST fixture failed')
        results.append({'tool_id': entry.tool.tool_id, 'probe': 'READY', 'transport': 'files', 'diagnostics': 1})
    return results


def build(output, *, node=None, dependencies=None, npm_cli=None, platform=None, progress=None):
    selected = platform or current_platform()
    if selected not in PLATFORMS or selected != current_platform():
        raise ValueError('Build companions on their native platform and architecture')
    output = Path(output).absolute(); output.mkdir(parents=True, exist_ok=True)
    archive_name = 'devsift-analyzers-' + selected + '.zip'
    if (output / archive_name).exists() or (output / (archive_name + '.sha256')).exists():
        raise ValueError('Refusing to replace existing analyzer companion')
    progress = progress or Progress(operation='analyzer build')
    dotnet = Path(shutil.which('dotnet') or '').resolve(strict=True)
    go = Path(shutil.which('go') or '').resolve(strict=True)
    node = Path(node or shutil.which('node') or '').resolve(strict=True)
    if _capture([dotnet, '--version'], ROOT / 'native/dotnet') != '9.0.205':
        raise ValueError('Owned analyzer build requires SDK 9.0.205')
    if _capture([go, 'version'], ROOT).split()[2] != 'go1.21.3':
        raise ValueError('Owned analyzer build requires Go 1.21.3')
    node_version = _capture([node, '--version'], ROOT)
    if not node_version.startswith('v24.'):
        raise ValueError('Companion runtime must be Node 24')
    node_license = _runtime_license(node)
    environment = dict(os.environ, DOTNET_NOLOGO='1', DOTNET_CLI_TELEMETRY_OPTOUT='1',
                       GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', CGO_ENABLED='0', GOWORK='off',
                       GOOS={'windows': 'windows', 'linux': 'linux', 'macos': 'darwin'}[selected.split('-')[0]],
                       GOARCH={'x64': 'amd64', 'arm64': 'arm64'}[selected.split('-')[1]])
    suffix = '.exe' if selected.startswith('windows-') else ''
    rid = selected.replace('windows-', 'win-').replace('macos-', 'osx-')
    log = output / (archive_name + '.build.log')
    with tempfile.TemporaryDirectory(prefix='devsift-analyzers-') as temporary:
        stage = Path(temporary) / 'payload'; stage.mkdir()
        packages = ROOT / '.devsift/local/analyzer-nuget'
        for folder, project in (('dotnet', 'DevSift.Roslyn'), ('sql', 'DevSift.Sql')):
            directory = ROOT / 'native' / folder
            _run([dotnet, 'publish', project + '.csproj', '-c', 'Release', '-r', rid, '--self-contained', 'true',
                  '-p:UseAppHost=true', '--source', 'https://api.nuget.org/v3/index.json', '--packages', packages,
                  '-o', stage / folder], directory, progress,
                 'Size unknown | downloading .NET runtime dependencies and building ' + folder, log, environment=environment)
        (stage / 'go').mkdir()
        _run([go, 'build', '-trimpath', '-buildvcs=false', '-o', stage / 'go' / ('devsift-go' + suffix), '.'],
             ROOT / 'native/go', progress, 'Building owned Go analyzer (offline)', log, environment=environment)
        frontend = ROOT / 'native/frontend'
        if dependencies is None:
            if npm_cli is None:
                candidates = (node.parent / 'node_modules/npm/bin/npm-cli.js', node.parent.parent / 'lib/node_modules/npm/bin/npm-cli.js')
                npm_cli = next((path for path in candidates if path.is_file()), None)
            if npm_cli is None:
                raise ValueError('Explicit trusted npm CLI required')
            _run([node, npm_cli, 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], frontend, progress,
                 'Size unknown | downloading owned frontend dependencies', log)
            dependencies = frontend / 'node_modules'
        progress.update(70, 'Copying runtime files and third-party license evidence')
        for name in ('analyze.cjs', 'package.json', 'package-lock.json'):
            copy_file(frontend / name, stage / 'frontend' / name)
        copy_file(node, stage / 'frontend' / ('node' + suffix))
        copy_tree(Path(dependencies), stage / 'frontend/node_modules', skip_bins=True)
        licenses = stage / 'licenses'; licenses.mkdir()
        copy_file(node_license, licenses / 'Node-LICENSE.txt')
        dotnet_root = dotnet.parent
        for name in ('LICENSE.txt', 'ThirdPartyNotices.txt'):
            copy_file(dotnet_root / name, licenses / ('dotnet-' + name))
        go_root = Path(_capture([go, 'env', 'GOROOT'], ROOT))
        copy_file(go_root / 'LICENSE', licenses / 'Go-LICENSE.txt')
        nuspec = packages / 'microsoft.sqlserver.transactsql.scriptdom/161.8901.0/microsoft.sqlserver.transactsql.scriptdom.nuspec'
        copy_file(nuspec, licenses / 'ScriptDOM-package.nuspec')
        entries = _tools(stage, suffix)
        progress.update(80, 'Probing bundled runtimes and analyzing owned AST fixtures')
        verified = smoke(entries)
        _json(stage / 'manifest-template.json', _template(entries, stage, selected))
        dependencies_inventory = []
        for path in sorted((stage / 'frontend/node_modules').rglob('package.json')):
            value = json.loads(path.read_text(encoding='utf-8'))
            if 'name' in value and 'version' in value:
                dependencies_inventory.append({'name': value['name'], 'version': value['version'],
                    'license': value.get('license', 'NOASSERTION'), 'path': path.relative_to(stage).as_posix()})
        licenses.joinpath('NOTICE.txt').write_text(
            'DevSift project license: NOASSERTION (unselected). No redistribution approval is asserted.\n'
            '.NET runtime/Roslyn: see dotnet-LICENSE and ThirdPartyNotices. Go runtime: see Go-LICENSE.\n'
            'Node runtime: see Node-LICENSE (includes bundled third-party notices).\n'
            'ScriptDOM 161.8901.0 declares MIT in its original NuGet metadata; license URL https://licenses.nuget.org/MIT.\n'
            'Frontend dependency license/notice files are preserved alongside their packages.\n'
            'This is a dependency/artifact inventory, not a claim of licensing approval or a complete legal audit.\n', encoding='utf-8')
        _json(stage / 'dependency-inventory.json', {'schema_version': '1', 'project_license': 'NOASSERTION',
            'redistribution_approved': False, 'node_version': node_version,
            'native_engines': {entry.tool.tool_id: dict(entry.tool.engine_versions) for entry in entries},
            'frontend_dependencies': dependencies_inventory})
        source_sha = _capture(['git', 'rev-parse', 'HEAD'], ROOT)
        _json(stage / 'build-provenance.json', {'schema_version': '1', 'platform': selected, 'source_commit': source_sha,
            'builder_sha256': file_digest(Path(__file__)), 'runtime_included': True, 'sdks_included': False,
            'project_code_built': False, 'probe_and_ast_fixtures': verified,
            'node_modules_bin_excluded': True, 'redistribution_approved': False})
        members = sorted(path for path in stage.rglob('*') if path.is_file())
        _json(stage / 'inventory.json', {'schema_version': '1', 'platform': selected,
            'files': [{'path': path.relative_to(stage).as_posix(), 'size': path.stat().st_size,
                       'sha256': file_digest(path)} for path in members],
            'self_digest': 'Covered by the independently supplied archive SHA256; this list excludes inventory.json itself.'})
        progress.update(90, 'Compressing verified analyzer companion')
        archive_path = output / archive_name
        with zipfile.ZipFile(archive_path, 'x', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    _plain(path)
                    archive.write(path, path.relative_to(stage).as_posix())
        archive_hash = file_digest(archive_path)
        (output / (archive_name + '.sha256')).write_text(archive_hash + '  ' + archive_name + '\n', encoding='ascii')
    return archive_path, archive_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--node', type=Path)
    parser.add_argument('--dependencies', type=Path)
    parser.add_argument('--npm-cli', type=Path)
    parser.add_argument('--platform', choices=PLATFORMS)
    args = parser.parse_args()
    with Progress(operation='analyzer build') as progress:
        try:
            archive, digest = build(**vars(args), progress=progress)
            progress.finish(message='Analyzer companion ready: ' + str(archive) + '\nSHA256: ' + digest)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            progress.fail('Owned analyzer companion build failed; inspect the private build log.')
            raise SystemExit(1) from None


if __name__ == '__main__':
    main()
