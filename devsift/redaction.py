"""Bounded defensive masking; not a comprehensive secret detector."""
from dataclasses import dataclass, field
import math
import re


MASK = "[REDACTED]"
_LIMIT = 2_000_000
_SENSITIVE = re.compile(r"^(?:password|passwd|secret|token|api[_-]?key|authorization|credential)s?$", re.I)
_PATTERNS = (
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,255}\b"), MASK),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), MASK),
    (re.compile(r"(?i)(\bBearer\s+)(?!\[REDACTED\])[^\s\"'<>]{8,4096}"), r"\g<1>" + MASK),
    (re.compile(r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*)(?:\"[^\"\r\n]{1,4096}\"|'[^'\r\n]{1,4096}'|(?!\[REDACTED\])[^\s,;]{1,4096})"), r"\g<1>" + MASK),
    (re.compile(r"(?i)(https?://)[^/@\s:]{1,256}:[^/@\s]{1,4096}@"), r"\g<1>" + MASK + "@"),
)


class RedactionError(ValueError):
    """Safe failure that never includes input values or object representations."""


def _fail():
    raise RedactionError("unsupported or excessive redaction input") from None


@dataclass(frozen=True)
class Redactor:
    secrets: tuple[str, ...] = field(default=(), repr=False)

    def __post_init__(self):
        if (not isinstance(self.secrets, (tuple, list)) or len(self.secrets) > 256
                or any(type(value) is not str or not value or len(value) > 4096 for value in self.secrets)):
            _fail()
        object.__setattr__(self, "secrets", tuple(sorted(set(self.secrets), key=lambda value: (-len(value), value))))

    def text(self, value):
        if type(value) is not str or len(value) > _LIMIT:
            _fail()
        # Preserve existing masks, including when an explicit sensitive value
        # happens to be a substring of the marker itself.
        for secret in self.secrets:
            value = MASK.join(piece.replace(secret, MASK) for piece in value.split(MASK))
        for pattern, replacement in _PATTERNS:
            value = pattern.sub(replacement, value)
        return value

    def redact(self, value):
        """Return a fresh JSON-compatible tree, including masked dictionary keys.

        Sensitive key values are masked wholesale. Reject cycles, excessive
        depth/size, unsupported objects and key collisions instead of repr/logging.
        """
        active = set()
        count = 0
        size = 0

        def visit(item, depth):
            nonlocal count, size
            count += 1
            if depth > 32 or count > 20_000:
                _fail()
            if type(item) is str:
                size += len(item)
                if size > _LIMIT:
                    _fail()
                return self.text(item)
            if item is None or type(item) in (bool, int):
                return item
            if type(item) is float:
                if not math.isfinite(item):
                    _fail()
                return item
            if type(item) not in (dict, list, tuple) or id(item) in active:
                _fail()
            active.add(id(item))
            try:
                if type(item) in (list, tuple):
                    return [visit(child, depth + 1) for child in item]
                result = {}
                for key, child in item.items():
                    if type(key) is not str:
                        _fail()
                    masked_key = visit(key, depth + 1)
                    if masked_key in result:
                        _fail()
                    result[masked_key] = MASK if _SENSITIVE.fullmatch(key) else visit(child, depth + 1)
                return result
            finally:
                active.remove(id(item))

        return visit(value, 0)
