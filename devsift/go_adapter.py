"""Explicit configuration of an already-built, pinned Go AST helper."""
from pathlib import Path

from .native_host import ToolDefinition, file_digest
from .process_runner import ProcessSpec


def make_tool(executable: str) -> ToolDefinition:
    if type(executable) is not str:
        raise ValueError('Explicit absolute Go helper path required')
    try:
        path = Path(executable)
        if not path.is_absolute():
            raise ValueError('Absolute helper path required')
        path = path.resolve()
        digest = file_digest(path)
        return ToolDefinition('devsift-go', '1.0.0', ('go',), ProcessSpec(str(path)),
                              digest, ((str(path), digest),), (('go', 'go1.21.3'),))
    except (OSError, ValueError, RuntimeError):
        raise ValueError('Pinned Go helper unavailable') from None
