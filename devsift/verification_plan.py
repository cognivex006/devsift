"""Read-only Git measurement and declared evidence comparison, never approval."""
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .change_budget import BudgetDecision, BudgetLimits, ChangeEstimate, ChangePlan, assess_plan
from .evidence import Region, SourceLocation
from .git_changes import _blob, _git, _resolve, _tree
from .redaction import Redactor
from .registry import RULES


class VerificationError(ValueError):
    """Fixed private failure; no paths, source, records or Git stderr exposed."""


def _require(condition):
    if not condition:
        raise VerificationError("invalid or unavailable verification evidence") from None


def _sha(value):
    _require(type(value) is str and re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", value) is not None)


def _digest(value):
    _require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value) is not None)


def _identifier(value):
    _require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is not None)
    _require(Redactor().text(value) == value)


def _common(record):
    _identifier(record.case_id)
    _digest(record.scope_digest)


def _fields(value, fields):
    _require(type(value) is dict and set(value) == set(fields) | {"schema_version", "kind"})
    _require(type(value["schema_version"]) is str and value["schema_version"] == "1")


@dataclass(frozen=True)
class DiagnosticRecord:
    """Declared analyzer observations; completeness is not execution provenance."""
    case_id: str = field(repr=False)
    source_sha: str
    scope_digest: str
    analyzer_id: str
    analyzer_version: str
    complete: bool
    findings: tuple[tuple[str, str], ...]

    def __post_init__(self):
        _common(self)
        _sha(self.source_sha)
        _identifier(self.analyzer_id)
        _identifier(self.analyzer_version)
        _require(type(self.complete) is bool and type(self.findings) in (tuple, list)
                 and len(self.findings) <= 1000)
        findings = []
        for item in self.findings:
            _require(type(item) in (tuple, list) and len(item) == 2)
            rule, fingerprint = item
            _require(type(rule) is str and rule in RULES)
            _digest(fingerprint)
            findings.append((rule, fingerprint))
        _require(len(set(findings)) == len(findings))
        object.__setattr__(self, "findings", tuple(sorted(findings)))

    def to_dict(self):
        return {"schema_version": "1", "kind": "diagnostic", "case_id": self.case_id,
                "source_sha": self.source_sha, "scope_digest": self.scope_digest,
                "analyzer_id": self.analyzer_id, "analyzer_version": self.analyzer_version,
                "complete": self.complete, "findings": [list(item) for item in self.findings]}


@dataclass(frozen=True)
class RegressionRecord:
    """External test declaration only; pass does not prove that a test ran."""
    case_id: str = field(repr=False)
    before_sha: str
    after_sha: str
    scope_digest: str
    status: str

    def __post_init__(self):
        _common(self)
        _sha(self.before_sha)
        _sha(self.after_sha)
        _require(type(self.status) is str and self.status in ("pass", "fail", "unknown"))

    def to_dict(self):
        return {"schema_version": "1", "kind": "regression", "case_id": self.case_id,
                "before_sha": self.before_sha, "after_sha": self.after_sha,
                "scope_digest": self.scope_digest, "status": self.status}


@dataclass(frozen=True)
class RollbackRecord:
    """Bounded proposed restore target; no command or rollback execution."""
    case_id: str = field(repr=False)
    before_sha: str
    after_sha: str
    scope_digest: str
    action: str

    def __post_init__(self):
        _common(self)
        _sha(self.before_sha)
        _sha(self.after_sha)
        _require(type(self.action) is str and self.action == "restore_before_commit")

    def to_dict(self):
        return {"schema_version": "1", "kind": "rollback", "case_id": self.case_id,
                "before_sha": self.before_sha, "after_sha": self.after_sha,
                "scope_digest": self.scope_digest, "action": self.action}


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value)
        value[key] = item
    return value


def load_record(text):
    """Strict bounded external JSON; every accepted record remains declared."""
    _require(type(text) is str and len(text) <= 262144)
    try:
        value = json.loads(text, object_pairs_hook=_pairs,
                           parse_constant=lambda _: _require(False))
        _require(type(value) is dict and type(value.get("kind")) is str)
        kind = value["kind"]
        classes = {"diagnostic": DiagnosticRecord, "regression": RegressionRecord, "rollback": RollbackRecord}
        _require(kind in classes)
        cls = classes[kind]
        fields = tuple(cls.__dataclass_fields__)
        _fields(value, fields)
        return cls(**{key: value[key] for key in fields})
    except (ValueError, TypeError, RecursionError, OverflowError):
        _require(False)


_SEAL = object()


@dataclass(frozen=True, init=False)
class GitMeasurement:
    """Factory-only local Git proof; serialized representations cannot restore it."""
    before_sha: str
    after_sha: str
    paths: tuple[str, ...] = field(repr=False)
    files: int
    added_lines: int
    removed_lines: int
    scope_digest: str
    _root: str = field(repr=False)

    def __init__(self, token=None, **values):
        _require(token is _SEAL and set(values) == set(self.__dataclass_fields__))
        for key, value in values.items():
            object.__setattr__(self, key, value)

    def to_dict(self):
        return {"schema_version": "1", "before_sha": self.before_sha, "after_sha": self.after_sha,
                "paths": list(self.paths), "files": self.files, "added_lines": self.added_lines,
                "removed_lines": self.removed_lines, "scope_digest": self.scope_digest,
                "counts_basis": "verified_git_diff"}


def _paths(values):
    _require(type(values) in (tuple, list) and len(values) <= 256)
    for value in values:
        _require(type(value) is str and len(value) <= 1024 and Redactor().text(value) == value)
        SourceLocation("verification", "0" * 40, value, Region(1, 1, 1, 1))
    _require(len(set(values)) == len(values))
    return tuple(sorted(values))


def verify_revision_pair(repo_root, before_sha, after_sha, expected_paths):
    """Measure the complete immutable pair, ignoring dirty working files.

    No external diff/textconv/filter, rename guessing, network, locks or writes.
    Git's LF numstat is the measure; binary and non-regular changes fail closed.
    """
    try:
        _sha(before_sha)
        _sha(after_sha)
        paths = _paths(expected_paths)
        root = Path(repo_root).resolve(strict=True)
        _require(Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root)
        config = _git(root, "config", "--includes", "--null", "--list").lower().split(b"\0")
        _require(not any(item.startswith(b"extensions.partialclone\n") or
                         item.split(b"\n", 1)[0].endswith(b".promisor") for item in config))
        _require(_git(root, "rev-parse", "--is-shallow-repository").strip() == b"false")
        _require(_resolve(root, before_sha) == before_sha and _resolve(root, after_sha) == after_sha)
        old, new = _tree(root, before_sha), _tree(root, after_sha)
        actual = tuple(sorted(path for path in old.keys() | new.keys() if old.get(path) != new.get(path)))
        _require(actual == paths)
        total = 0
        for path in paths:
            for tree in (old, new):
                if path in tree:
                    raw = _blob(root, tree[path])
                    total += len(raw)
                    _require(total <= 2_000_000 and b"\0" not in raw)
                    raw.decode("utf-8")
        data = _git(root, "diff", "--numstat", "-z", "--no-renames", "--no-ext-diff",
                    "--no-textconv", before_sha, after_sha, "--")
        rows = []
        for entry in data.split(b"\0"):
            if entry:
                added, removed, path = entry.split(b"\t", 2)
                _require(added.isdigit() and removed.isdigit())
                rows.append((path.decode("utf-8"), int(added), int(removed)))
        _require(tuple(sorted(row[0] for row in rows)) == paths)
        added, removed = sum(row[1] for row in rows), sum(row[2] for row in rows)
        ChangeEstimate(len(paths), added, removed)
        payload = ["devsift-git-measurement-v1", before_sha, after_sha, sorted(rows)]
        digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        return GitMeasurement(_SEAL, before_sha=before_sha, after_sha=after_sha, paths=paths,
                              files=len(paths), added_lines=added, removed_lines=removed,
                              scope_digest=digest, _root=str(root))
    except (OSError, ValueError, TypeError, RuntimeError, UnicodeError, subprocess.SubprocessError):
        _require(False)


@dataclass(frozen=True)
class VerificationComparison:
    budget: BudgetDecision
    reasons: tuple[str, ...]
    added: tuple[tuple[str, str], ...]
    removed: tuple[tuple[str, str], ...]
    persisting: tuple[tuple[str, str], ...]
    counts_basis: str

    def __post_init__(self):
        allowed = {"independent_diagnostic_capture_required", "independent_regression_capture_required",
                   "git_measurement_missing", "diagnostic_record_missing", "diagnostic_analysis_incomplete",
                   "regression_record_missing", "regression_not_declared_pass", "rollback_record_missing",
                   "budget_incomplete", "separate_approval_required"}
        _require(type(self.budget) is BudgetDecision and type(self.reasons) is tuple
                 and len(self.reasons) <= len(allowed))
        _require(all(type(reason) is str and reason in allowed for reason in self.reasons)
                 and len(set(self.reasons)) == len(self.reasons))
        _require(type(self.counts_basis) is str and self.counts_basis in ("declared_estimate", "verified_git_diff"))
        for group in (self.added, self.removed, self.persisting):
            _require(type(group) is tuple and len(group) <= 1000)
            for pair in group:
                _require(type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str and pair[0] in RULES)
                _digest(pair[1])
            _require(len(set(group)) == len(group))

    @property
    def status(self):
        return "incomplete"

    @property
    def verification_pending(self):
        return True

    @property
    def write_authorized(self):
        return False

    @property
    def execution_authorized(self):
        return False

    def to_dict(self):
        return {"schema_version": "1", "status": "incomplete", "budget": self.budget.to_dict(),
                "reasons": list(self.reasons), "added": [list(item) for item in self.added],
                "removed": [list(item) for item in self.removed],
                "persisting": [list(item) for item in self.persisting],
                "counts_basis": self.counts_basis, "diagnostics_basis": "declared",
                "regression_basis": "declared", "verification_pending": True,
                "requires_case_authorization": True, "write_authorized": False,
                "execution_authorized": False}


def compare_verification(plan, limits, measurement, before, after, regression, rollback, *, repo_root):
    """Compare declarations after exact pair/case/scope checks; never attest tests.

    Recheck local Git proof on every call. Actual counts replace estimates only;
    no label becomes verified risk, no diagnostic delta becomes a proven fix.
    """
    _require(type(plan) is ChangePlan and type(limits) is BudgetLimits and len(plan.case_ids) == 1)
    _require(measurement is None or type(measurement) is GitMeasurement)
    expected = (DiagnosticRecord, DiagnosticRecord, RegressionRecord, RollbackRecord)
    for record, cls in zip((before, after, regression, rollback), expected):
        _require(record is None or type(record) is cls)
        if record is not None:
            _require(record.case_id == plan.case_ids[0])
    if measurement is not None:
        try:
            _require(str(Path(repo_root).resolve(strict=True)) == measurement._root)
        except (OSError, ValueError, RuntimeError):
            _require(False)
        current = verify_revision_pair(repo_root, measurement.before_sha, measurement.after_sha, measurement.paths)
        _require(current == measurement)
    records = tuple(record for record in (before, after, regression, rollback) if record is not None)
    scopes = {record.scope_digest for record in records}
    old_shas = ({before.source_sha} if before else set()) | {record.before_sha for record in (regression, rollback) if record}
    new_shas = ({after.source_sha} if after else set()) | {record.after_sha for record in (regression, rollback) if record}
    if measurement:
        scopes.add(measurement.scope_digest)
        old_shas.add(measurement.before_sha)
        new_shas.add(measurement.after_sha)
    _require(len(scopes) <= 1 and len(old_shas) <= 1 and len(new_shas) <= 1)
    if before and after:
        _require((before.analyzer_id, before.analyzer_version) == (after.analyzer_id, after.analyzer_version))
    budget_plan = plan if measurement is None else replace(plan, estimate=ChangeEstimate(
        measurement.files, measurement.added_lines, measurement.removed_lines))
    budget = assess_plan(budget_plan, limits)
    reasons = ["independent_diagnostic_capture_required", "independent_regression_capture_required"]
    if measurement is None:
        reasons.append("git_measurement_missing")
    if before is None or after is None:
        reasons.append("diagnostic_record_missing")
    if (before and not before.complete) or (after and not after.complete):
        reasons.append("diagnostic_analysis_incomplete")
    if regression is None:
        reasons.append("regression_record_missing")
    elif regression.status != "pass":
        reasons.append("regression_not_declared_pass")
    if rollback is None:
        reasons.append("rollback_record_missing")
    if budget.status == "incomplete":
        reasons.append("budget_incomplete")
    if budget.separate_approval_required:
        reasons.append("separate_approval_required")
    added = removed = persisting = ()
    if before and after and before.complete and after.complete:
        old, new = set(before.findings), set(after.findings)
        added, removed, persisting = tuple(sorted(new - old)), tuple(sorted(old - new)), tuple(sorted(old & new))
    return VerificationComparison(budget, tuple(reasons), added, removed, persisting,
                                  "verified_git_diff" if measurement else "declared_estimate")
