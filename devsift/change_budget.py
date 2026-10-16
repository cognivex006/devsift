"""Read-only declared change-budget planning; never an editing permission gate."""
from dataclasses import dataclass, field
import json
import re

from .redaction import Redactor


class BudgetError(ValueError):
    """Invalid bounded planning input; messages never contain caller data."""


def _fail():
    raise BudgetError("invalid or excessive change-budget input") from None


def _object(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        _fail()


def _count(value):
    if value is not None and (type(value) is not int or not 0 <= value < 2**63):
        _fail()


def _enum(value, choices):
    if type(value) is not str or value not in choices:
        _fail()


_COUNTS = ("files", "added_lines", "removed_lines")
_LIMITS = ("max_files", "max_added_lines", "max_removed_lines")
_LIFECYCLES = ("NEW", "MODIFIED_INTRODUCED", "MODIFIED_PREEXISTING",
               "LEGACY_UNCHANGED", "UNKNOWN")
_PLAN = ("schema_version", "case_ids", "lifecycle_class", "estimate", "refactor",
         "risk_if_changed", "consumer_impact")


@dataclass(frozen=True)
class BudgetLimits:
    """Operator-selected ceilings. None is unspecified, never unlimited."""
    max_files: int | None = None
    max_added_lines: int | None = None
    max_removed_lines: int | None = None

    def __post_init__(self):
        for key in _LIMITS:
            _count(getattr(self, key))

    def to_dict(self):
        return {key: getattr(self, key) for key in _LIMITS}

    @classmethod
    def from_dict(cls, value):
        _object(value, _LIMITS)
        return cls(**value)


@dataclass(frozen=True)
class ChangeEstimate:
    """Caller estimates, not measured changes or immutable source proof."""
    files: int | None = None
    added_lines: int | None = None
    removed_lines: int | None = None

    def __post_init__(self):
        for key in _COUNTS:
            _count(getattr(self, key))

    def to_dict(self):
        return {key: getattr(self, key) for key in _COUNTS}

    @classmethod
    def from_dict(cls, value):
        _object(value, _COUNTS)
        return cls(**value)


@dataclass(frozen=True)
class ChangePlan:
    """Declared planning labels; none independently verifies source or impact."""
    case_ids: tuple[str, ...] = field(repr=False)
    lifecycle_class: str
    estimate: ChangeEstimate
    refactor: bool
    risk_if_changed: str
    consumer_impact: str

    def __post_init__(self):
        if type(self.case_ids) not in (tuple, list) or not 1 <= len(self.case_ids) <= 1000:
            _fail()
        redactor = Redactor()
        for value in self.case_ids:
            if (type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value)
                    or redactor.text(value) != value):
                _fail()
        if len(set(self.case_ids)) != len(self.case_ids):
            _fail()
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        _enum(self.lifecycle_class, _LIFECYCLES)
        _enum(self.risk_if_changed, ("low", "moderate", "high", "unknown"))
        _enum(self.consumer_impact, ("none", "bounded", "broad", "unknown"))
        if type(self.estimate) is not ChangeEstimate or type(self.refactor) is not bool:
            _fail()

    def to_dict(self):
        return {"schema_version": "1", "case_ids": list(self.case_ids),
                "lifecycle_class": self.lifecycle_class, "estimate": self.estimate.to_dict(),
                "refactor": self.refactor, "risk_if_changed": self.risk_if_changed,
                "consumer_impact": self.consumer_impact}

    @classmethod
    def from_dict(cls, value):
        _object(value, _PLAN)
        if type(value["schema_version"]) is not str or value["schema_version"] != "1":
            _fail()
        if type(value["case_ids"]) is not list:
            _fail()
        return cls(value["case_ids"], value["lifecycle_class"],
                   ChangeEstimate.from_dict(value["estimate"]), value["refactor"],
                   value["risk_if_changed"], value["consumer_impact"])


@dataclass(frozen=True)
class BudgetDecision:
    """Planning disposition only; unfulfilled approval is never a grant."""
    status: str
    reasons: tuple[str, ...]
    legacy_advisory: bool
    separate_approval_required: bool

    def __post_init__(self):
        _enum(self.status, ("incomplete", "separate_approval_required", "bounded_plan_review"))
        allowed = {"lifecycle_unknown", "change_risk_unknown", "consumer_impact_unknown",
                   "refactor", "batch_plan", "high_change_risk", "broad_consumer_impact"}
        allowed.update(count + suffix for count in _COUNTS
                       for suffix in ("_estimate_missing", "_limit_missing", "_over_budget"))
        if (type(self.reasons) is not tuple or len(self.reasons) > len(allowed)
                or any(type(reason) is not str or reason not in allowed for reason in self.reasons)
                or len(set(self.reasons)) != len(self.reasons)
                or type(self.legacy_advisory) is not bool
                or type(self.separate_approval_required) is not bool):
            _fail()

    @property
    def write_authorized(self):
        return False

    @property
    def execution_authorized(self):
        return False

    @property
    def requires_case_authorization(self):
        return True

    @property
    def verification_pending(self):
        return True

    @property
    def counts_basis(self):
        return "declared_estimate"

    @property
    def labels_basis(self):
        return "declared"

    def to_dict(self):
        return {"schema_version": "1", "status": self.status, "reasons": list(self.reasons),
                "legacy_advisory": self.legacy_advisory,
                "separate_approval_required": self.separate_approval_required,
                "write_authorized": False, "execution_authorized": False,
                "requires_case_authorization": True, "verification_pending": True,
                "counts_basis": "declared_estimate", "labels_basis": "declared"}


def assess_plan(plan, limits):
    """Compare estimates with explicit limits without reading or modifying files.

    Unknowns dominate the status; separately required approval remains visible.
    This never changes finding severity/enforcement or critical security review.
    """
    if type(plan) is not ChangePlan or type(limits) is not BudgetLimits:
        _fail()
    unknown = []
    separate = []
    if plan.lifecycle_class == "UNKNOWN":
        unknown.append("lifecycle_unknown")
    if plan.risk_if_changed == "unknown":
        unknown.append("change_risk_unknown")
    if plan.consumer_impact == "unknown":
        unknown.append("consumer_impact_unknown")
    for count, limit in zip(_COUNTS, _LIMITS):
        estimate, ceiling = getattr(plan.estimate, count), getattr(limits, limit)
        if estimate is None:
            unknown.append(count + "_estimate_missing")
        if ceiling is None:
            unknown.append(count + "_limit_missing")
        if estimate is not None and ceiling is not None and estimate > ceiling:
            separate.append(count + "_over_budget")
    if plan.refactor:
        separate.append("refactor")
    if len(plan.case_ids) != 1:
        separate.append("batch_plan")
    if plan.risk_if_changed == "high":
        separate.append("high_change_risk")
    if plan.consumer_impact == "broad":
        separate.append("broad_consumer_impact")
    status = ("incomplete" if unknown else "separate_approval_required" if separate
              else "bounded_plan_review")
    return BudgetDecision(status, tuple(unknown + separate),
                          plan.lifecycle_class in ("LEGACY_UNCHANGED", "MODIFIED_PREEXISTING"),
                          bool(separate))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail()
        result[key] = value
    return result


def load_plan(text):
    """Decode bounded JSON text, never a filename; reject duplicate keys."""
    if type(text) is not str or len(text) > 65536:
        _fail()
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=lambda _: _fail())
        return ChangePlan.from_dict(value)
    except (ValueError, TypeError, RecursionError, OverflowError):
        _fail()
