"""Pinned ScriptDom parser factory; setup/build is never part of analysis."""
import json
from pathlib import Path

from .native_host import ToolDefinition, file_digest
from .process_runner import ProcessSpec


SCRIPT_DOM_VERSION = "161.8901.0"
ARTIFACTS = ("DevSift.Sql.dll", "DevSift.Sql.deps.json", "DevSift.Sql.runtimeconfig.json",
             "Microsoft.SqlServer.TransactSql.ScriptDom.dll")


def make_tool(dotnet_executable, artifact_dir):
    """Capture caller-trusted runtime/helper/dependency hashes after explicit setup."""
    try:
        executable, directory = Path(dotnet_executable), Path(artifact_dir)
        if not executable.is_absolute() or not directory.is_absolute():
            raise ValueError()
        directory = directory.resolve(strict=True)
        paths = tuple(directory / name for name in ARTIFACTS)
        if any(path.is_symlink() or not path.is_file() for path in paths):
            raise ValueError()
        deps = json.loads(paths[1].read_text(encoding="utf-8"))
        key = "Microsoft.SqlServer.TransactSql.ScriptDom/" + SCRIPT_DOM_VERSION
        if key not in deps["libraries"] or any(
            item.startswith("Microsoft.SqlServer.TransactSql.ScriptDom/") and item != key
            for item in deps["libraries"]
        ):
            raise ValueError()
        return ToolDefinition("devsift-sql", "1.1.0", ("sql",),
                              ProcessSpec(str(executable), (str(paths[0]),), max_stdin_bytes=2_000_000),
                              file_digest(executable), tuple((str(path), file_digest(path)) for path in paths),
                              (("scriptdom", SCRIPT_DOM_VERSION),))
    except (OSError, ValueError, KeyError, TypeError):
        raise ValueError("SQL parser artifacts unavailable or unpinned") from None
