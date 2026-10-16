"""Explicit setup factory for pinned ESLint/TypeScript parser artifacts."""
from pathlib import Path

from .native_host import ToolDefinition, file_digest
from .process_runner import ProcessSpec


def make_tool(node_executable, package_dir=None):
    """Caller explicitly trusts setup runtime/package; scans use frozen pins."""
    try:
        node = Path(node_executable)
        package = (Path(package_dir) if package_dir is not None
                   else Path(__file__).resolve().parents[1] / 'native' / 'frontend')
        if not node.is_absolute() or not package.is_absolute():
            raise ValueError()
        node, package = node.resolve(strict=True), package.resolve(strict=True)
        artifacts = tuple((str(package / name), file_digest(package / name))
                          for name in ('analyze.cjs', 'package.json', 'package-lock.json'))
        return ToolDefinition('devsift-typescript', '1.1.0', ('typescript', 'javascript'),
                              ProcessSpec(str(node), (str(package / 'analyze.cjs'),), max_stdin_bytes=2_000_000),
                              file_digest(node), artifacts,
                              (('eslint', '10.12.0'), ('parser', '8.71.2'), ('typescript', '6.0.3')))
    except (OSError, ValueError, TypeError):
        raise ValueError('Frontend parser artifacts unavailable or unpinned') from None
