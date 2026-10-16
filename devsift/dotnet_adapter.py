"""Explicit caller-trusted Roslyn artifact configuration; no build/discovery."""
from pathlib import Path

from .native_host import ToolDefinition, file_digest
from .process_runner import ProcessSpec


def make_tool(dotnet_executable: str, artifact_dir: Path) -> ToolDefinition:
    """Pin already-built trusted artifacts; never build/install a target project."""
    if type(dotnet_executable) is not str or not isinstance(artifact_dir, Path):
        raise ValueError('Explicit absolute native tool paths required')
    names = ('DevSift.Roslyn.dll', 'DevSift.Roslyn.deps.json', 'DevSift.Roslyn.runtimeconfig.json',
             'Microsoft.CodeAnalysis.dll', 'Microsoft.CodeAnalysis.CSharp.dll')
    try:
        runtime, directory = Path(dotnet_executable), artifact_dir
        if not runtime.is_absolute() or not directory.is_absolute():
            raise ValueError('Absolute native tool paths required')
        runtime, directory = runtime.resolve(), directory.resolve()
        artifacts = tuple((str(directory / name), file_digest(directory / name)) for name in names)
        return ToolDefinition('devsift-roslyn', '1.0.0', ('csharp',),
                              ProcessSpec(str(runtime), (str(directory / names[0]),), timeout_seconds=20,
                                          environment=(('DOTNET_NOLOGO', '1'),
                                                       ('DOTNET_CLI_TELEMETRY_OPTOUT', '1'),
                                                       ('DOTNET_SKIP_FIRST_TIME_EXPERIENCE', '1'))),
                              file_digest(runtime), artifacts, (('roslyn', '4.13.0.0'),))
    except (OSError, ValueError, RuntimeError):
        raise ValueError('Pinned Roslyn artifacts unavailable') from None
