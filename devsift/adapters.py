"""File language detection and capability negotiation, without analyzer execution."""
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

LANGUAGES = frozenset({'csharp', 'typescript', 'javascript', 'go', 'sql', 'python'})
_EXTENSIONS = {'.cs': 'csharp', '.ts': 'typescript', '.tsx': 'typescript',
               '.mts': 'typescript', '.cts': 'typescript', '.js': 'javascript',
               '.jsx': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
               '.go': 'go', '.sql': 'sql', '.py': 'python'}


def detect_language(path: str) -> str | None:
    return _EXTENSIONS.get(PurePosixPath(path).suffix.lower())


class SourceView(Protocol):
    """Adapter input is a snapshot, not a writable filesystem handle."""
    path: str
    status: str
    language: str | None
    content: bytes | None


@dataclass(frozen=True)
class AdapterCapability:
    adapter_id: str
    version: str
    languages: tuple[str, ...]
    available: bool

    def __post_init__(self):
        if (not isinstance(self.adapter_id, str) or not self.adapter_id.strip()
                or not isinstance(self.version, str) or not self.version.strip()
                or type(self.available) is not bool
                or type(self.languages) is not tuple or not self.languages
                or any(type(language) is not str or language not in LANGUAGES
                       for language in self.languages)
                or len(set(self.languages)) != len(self.languages)):
            raise ValueError('Invalid adapter identity, version, languages or availability')


@dataclass(frozen=True)
class AdapterDecision:
    path: str
    language: str | None
    status: str
    adapter_id: str | None = None
    version: str | None = None
    reason: str = ''


def negotiate(target: SourceView,
              capabilities: tuple[AdapterCapability, ...] = ()) -> AdapterDecision:
    """Supported means eligible to invoke later, never analyzed or passing.

    No default adapters are shipped. Supplying a capability is a trusted caller's
    declaration, not native-provider discovery or a sandbox guarantee.
    """
    if type(capabilities) is not tuple or any(not isinstance(cap, AdapterCapability) for cap in capabilities):
        raise ValueError('Capabilities must be AdapterCapability records')
    if len({cap.adapter_id for cap in capabilities}) != len(capabilities):
        raise ValueError('Duplicate adapter identity')
    if target.status in {'unsupported', 'binary', 'excluded'}:
        return AdapterDecision(target.path, target.language, 'skipped', reason=target.status)
    if target.status != 'ready' or target.language not in LANGUAGES or type(target.content) is not bytes:
        return AdapterDecision(target.path, target.language, 'incomplete', reason='Source unavailable')
    matching = sorted((cap for cap in capabilities if target.language in cap.languages),
                      key=lambda cap: (not cap.available, cap.adapter_id, cap.version))
    if not matching:
        return AdapterDecision(target.path, target.language, 'unavailable', reason='No registered analyzer')
    selected = matching[0]
    return AdapterDecision(target.path, target.language,
                           'supported' if selected.available else 'unavailable',
                           selected.adapter_id, selected.version,
                           'Capability declared; analysis not executed' if selected.available
                           else 'Registered analyzer unavailable')
