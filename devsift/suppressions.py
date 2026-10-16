"""Finding-scoped, expiring waivers; never authorize security escalation bypass."""
from dataclasses import dataclass
from datetime import datetime
import re

from .baseline import BaselineError, _digest, _fields, _parse, _text
from .registry import RULES, Severity


class SuppressionError(ValueError):
    pass


def _require(condition):
    if not condition:
        raise SuppressionError("invalid or expired suppression") from None


def _moment(value):
    _require(type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None)
    return value


@dataclass(frozen=True)
class Suppression:
    rule_id: str
    fingerprint: str
    owner: str
    reason: str
    ticket: str
    expires_at: str

    def __post_init__(self):
        try:
            _require(type(self.rule_id) is str and self.rule_id in RULES)
            rule = RULES[self.rule_id]
            _require(not (rule.security and rule.severity == Severity.CRITICAL))
            _digest(self.fingerprint)
            for name, maximum in (("owner", 256), ("reason", 2048), ("ticket", 256)):
                object.__setattr__(self, name, _text(getattr(self, name), maximum))
            _require(type(self.expires_at) is str and len(self.expires_at) <= 64
                     and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", self.expires_at) is not None)
            _moment(datetime.fromisoformat(self.expires_at))
        except (BaselineError, ValueError):
            raise SuppressionError("invalid or expired suppression") from None

    def valid_at(self, as_of):
        _require(_moment(as_of) < datetime.fromisoformat(self.expires_at))
        return True

    def matches(self, rule_id, fingerprint, *, as_of):
        self.valid_at(as_of)
        return self.rule_id == rule_id and self.fingerprint == fingerprint

    def to_dict(self):
        return {"schema_version": "1", **{name: getattr(self, name) for name in
                ("rule_id", "fingerprint", "owner", "reason", "ticket", "expires_at")}}

    @classmethod
    def from_dict(cls, data):
        try:
            _fields(data, ("schema_version", "rule_id", "fingerprint", "owner", "reason", "ticket", "expires_at"))
            _require(data["schema_version"] == "1")
            return cls(**{key: value for key, value in data.items() if key != "schema_version"})
        except BaselineError:
            raise SuppressionError("invalid or expired suppression") from None


def load_suppressions(text, *, as_of):
    """Parse text only; require deterministic explicit time and reject expiry."""
    _moment(as_of)
    try:
        data = _parse(text)
        _require(type(data) is list and len(data) <= 1000)
        entries = tuple(Suppression.from_dict(item) for item in data)
        _require(len({(entry.rule_id, entry.fingerprint) for entry in entries}) == len(entries))
        for entry in entries:
            entry.valid_at(as_of)
        return entries
    except BaselineError:
        raise SuppressionError("invalid or expired suppression") from None
