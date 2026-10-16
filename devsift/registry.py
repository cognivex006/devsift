"""Stable policy metadata, not a claim that rule detectors are implemented."""
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Severity(StrEnum):
    CRITICAL = "Critical"
    ERROR = "Error"
    WARNING = "Warning"
    SUGGESTION = "Suggestion"


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: Severity
    security: bool = False


_CATALOG = (
    Rule("HC001", "Literal external URL/IP/hostname in runtime code", Severity.ERROR),
    Rule("HC002", "Credential/API key/token literal", Severity.CRITICAL, True),
    Rule("HC003", "Environment-specific branch in domain logic", Severity.ERROR),
    Rule("HC004", "Unnamed business threshold/magic number", Severity.WARNING),
    Rule("HC005", "Machine-specific filesystem path", Severity.ERROR),
    Rule("CFG001", "Required configuration lacks validation/schema", Severity.ERROR),
    Rule("CFG002", "Duplicate/unused configuration key", Severity.WARNING),
    Rule("CFG003", "Secret in committed config or unsafe fallback", Severity.CRITICAL, True),
    Rule("COM001", "Commented-out executable code", Severity.ERROR),
    Rule("COM002", "Untracked TODO/FIXME/HACK", Severity.WARNING),
    Rule("COM003", "Redundant comments narrating obvious code", Severity.SUGGESTION),
    Rule("SEC001", "Logging secrets/PII", Severity.CRITICAL, True),
    Rule("SEC002", "Disabled TLS validation", Severity.CRITICAL, True),
    Rule("SEC003", "Dynamic SQL with untrusted input", Severity.CRITICAL, True),
    Rule("ARC001", "Forbidden cross-layer imports", Severity.ERROR),
    Rule("ARC002", "Duplicated business logic", Severity.SUGGESTION),
    Rule("ARC003", "Unapproved dependencies", Severity.ERROR),
    Rule("API001", "Unreviewed breaking API/schema change", Severity.ERROR),
    Rule("API002", "Retry/timeout values embedded in application flow", Severity.WARNING),
    Rule("LOG001", "Debug printing in runtime paths", Severity.WARNING),
    Rule("LOG002", "Swallowed exceptions", Severity.ERROR),
    Rule("TST001", "Changed behavior without suitable tests", Severity.ERROR),
    Rule("TST002", "Skipped test without ticket/expiry", Severity.ERROR),
)

RULES = MappingProxyType({rule.id: rule for rule in _CATALOG})
