"""Explicit trusted analyzer setup. Never called by scan or target configuration."""
import os
from pathlib import Path
import shutil
import subprocess
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]


def build():
    output = ROOT / '.devsift/local/tools'
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, DOTNET_NOLOGO='1', DOTNET_CLI_TELEMETRY_OPTOUT='1',
                       GOTOOLCHAIN='local', GOPROXY='off', GOSUMDB='off', CGO_ENABLED='0', GOWORK='off')

    def run(command, directory):
        return subprocess.run(command, cwd=directory, env=environment, check=True,
                              timeout=300, capture_output=True, text=True).stdout.strip()

    dotnet, go, node = (shutil.which(name) for name in ('dotnet', 'go', 'node'))
    if not all((dotnet, go, node)):
        raise RuntimeError('Setup requires dotnet, Go and Node installations')
    for folder, project in [('dotnet', 'DevSift.Roslyn'), ('sql', 'DevSift.Sql')]:
        directory = ROOT / 'native' / folder
        if run([dotnet, '--version'], directory) != '9.0.205':
            raise RuntimeError('Setup requires SDK 9.0.205')
        command = [dotnet, 'restore', project + '.csproj', '--configfile', 'NuGet.Config']
        if folder == 'sql':
            command += ['--locked-mode', '--packages', str(ROOT / '.devsift/local/nuget')]
        run(command, directory)
        run([dotnet, 'publish', project + '.csproj', '-c', 'Release', '--no-restore',
             '-o', str(output / folder)], directory)
    if run([go, 'version'], ROOT).split()[2] != 'go1.21.3':
        raise RuntimeError('Setup requires Go 1.21.3')
    (output / 'go').mkdir(exist_ok=True)
    binary = output / 'go' / ('devsift-go.exe' if os.name == 'nt' else 'devsift-go')
    run([go, 'build', '-trimpath', '-buildvcs=false', '-o', str(binary), '.'], ROOT / 'native/go')
    # Invoke npm through Node directly: no Windows .cmd shell or source hooks.
    npm = shutil.which('npm')
    if not npm:
        raise RuntimeError('Setup requires npm')
    npm_path = Path(npm).resolve()
    candidates = [npm_path.parent / 'node_modules/npm/bin/npm-cli.js',
                  npm_path.parent / '../lib/node_modules/npm/bin/npm-cli.js',
                  npm_path.parent / 'npm-cli.js']
    npm_cli = next((path.resolve() for path in candidates if path.is_file()), None)
    if npm_cli is None:
        raise RuntimeError('Cannot locate installed npm CLI')
    run([node, str(npm_cli), 'ci', '--ignore-scripts', '--no-audit', '--no-fund'], ROOT / 'native/frontend')
    # Setup records trusted pins once. Scans load these exact stored expectations
    # and never regenerate hashes from possibly replaced executables/artifacts.
    sys.path.insert(0, str(ROOT))
    from devsift.dotnet_adapter import make_tool as dotnet_tool
    from devsift.go_adapter import make_tool as go_tool
    from devsift.sql_adapter import make_tool as sql_tool
    from devsift.typescript_adapter import make_tool as typescript_tool
    from devsift.native_manifest import ConfiguredTool, manifest_bytes
    manifest = manifest_bytes((
        ConfiguredTool(dotnet_tool(str(Path(dotnet).resolve()), output / 'dotnet')),
        ConfiguredTool(go_tool(str(binary.resolve()))),
        ConfiguredTool(sql_tool(str(Path(dotnet).resolve()), output / 'sql'), 'tsql160'),
        ConfiguredTool(typescript_tool(str(Path(node).resolve()), ROOT / 'native/frontend')),
    ))
    destination = ROOT / '.devsift/local/native-manifest.json'
    digest = hashlib.sha256(manifest).hexdigest()
    destination.write_bytes(manifest)
    destination.with_suffix('.sha256').write_text(digest + '\n', encoding='ascii')
    print('Pinned native setup completed; manifest:', destination)
    print('Manifest SHA256:', digest)


if __name__ == '__main__':
    build()
