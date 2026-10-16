"""Conservative immutable Git source-origin attribution, not rule re-analysis."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .evidence import Region, SourceEvidence, SourceLocation, verify_source
from .redaction import Redactor
from .registry import RULES


class ProvenanceError(ValueError):
    """Safe contract failure without refs, snippets, paths or Git stderr."""


def _require(condition):
    if not condition:
        raise ProvenanceError("invalid provenance contract") from None


@dataclass(frozen=True)
class BaselineObservation:
    rule_id: str
    source_sha: str
    path: str
    findings: tuple[SourceEvidence, ...]
    complete: bool
    analyzer_id: str

    def __post_init__(self):
        _require(type(self.rule_id) is str and self.rule_id in RULES)
        SourceLocation("baseline", self.source_sha, self.path, Region(1, 1, 1, 1))
        _require(type(self.findings) in (tuple, list) and len(self.findings) <= 1000
                 and all(type(item) is SourceEvidence for item in self.findings))
        _require(type(self.complete) is bool and type(self.analyzer_id) is str
                 and 0 < len(self.analyzer_id) <= 256
                 and all(ord(char) >= 32 for char in self.analyzer_id))
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "source_sha", self.source_sha.lower())
        object.__setattr__(self, "analyzer_id", Redactor().text(self.analyzer_id))


@dataclass(frozen=True)
class Classification:
    lifecycle_class: str
    reason: str
    merge_base_sha: str | None = None
    head_sha: str | None = None
    fingerprint: str | None = None
    head_location: SourceLocation | None = None
    base_location: SourceLocation | None = None

    def to_dict(self):
        return {"lifecycle_class": self.lifecycle_class, "reason": self.reason,
                "merge_base_sha": self.merge_base_sha, "head_sha": self.head_sha,
                "fingerprint": self.fingerprint,
                "head_location": None if self.head_location is None else self.head_location.to_dict(),
                "base_location": None if self.base_location is None else self.base_location.to_dict()}


def _git(root, *args):
    environment = os.environ.copy()
    environment.update(GIT_NO_REPLACE_OBJECTS="1", GIT_LITERAL_PATHSPECS="1",
                       GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1")
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
                            env=environment, capture_output=True, timeout=10)
    if result.returncode or len(result.stdout) > 5_000_000:
        raise ProvenanceError("Git provenance unavailable")
    return result.stdout


def _resolve(root, ref):
    _require(type(ref) is str and 0 < len(ref) <= 1024 and all(ord(char) >= 32 for char in ref))
    sha = _git(root, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode("ascii").strip()
    SourceLocation("resolved", sha, "placeholder", Region(1, 1, 1, 1))
    return sha


def _tree(root, sha):
    entries = _git(root, "ls-tree", "-rz", sha).split(b"\0")
    if len(entries) > 1001:
        raise ProvenanceError("Git provenance unavailable")
    result = {}
    for entry in entries:
        if entry:
            metadata, path = entry.split(b"\t", 1)
            mode, kind, oid = metadata.split(b" ")
            result[path.decode("utf-8")] = (mode, kind, oid.decode("ascii"))
    return result


def _blob(root, entry):
    mode, kind, oid = entry
    _require(mode in (b"100644", b"100755") and kind == b"blob")
    if int(_git(root, "cat-file", "-s", oid)) > 2_000_000:
        raise ProvenanceError("Git provenance unavailable")
    return _git(root, "cat-file", "blob", oid)


def _lines(text):
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def _selected(text, region):
    lines = _lines(text)
    start = sum(map(len, lines[:region.start_line - 1])) + region.start_column - 1
    end = sum(map(len, lines[:region.end_line - 1])) + region.end_column - 1
    return text[start:end]


def _unique_mapping(old_text, new_text, region):
    old_lines, new_lines = _lines(old_text), _lines(new_text)
    selected = new_lines[region.start_line - 1:region.end_line]
    if not selected:
        return None

    def matches(lines):
        return [index for index in range(len(lines) - len(selected) + 1)
                if lines[index:index + len(selected)] == selected]

    old_matches, new_matches = matches(old_lines), matches(new_lines)
    if len(old_matches) != 1 or len(new_matches) != 1:
        return None
    offset = old_matches[0] - (region.start_line - 1)
    return Region(region.start_line + offset, region.start_column,
                  region.end_line + offset, region.end_column)


def classify(repo_root, base_ref, head_ref, rule_id, evidence, *, baseline=None, redactor=None):
    """Return proven source origin or UNKNOWN. Never infer semantic validity.

    Complete baseline absence is trusted caller analysis input, not a claim that
    this library ran an analyzer. Existing changed findings without that input
    remain UNKNOWN. No refs/index/source/baselines are written and no network used.
    """
    merge_base = head = fingerprint = location = None

    def result(lifecycle, reason, base_location=None):
        return Classification(lifecycle, reason, merge_base, head, fingerprint, location, base_location)

    try:
        _require(type(rule_id) is str and rule_id in RULES)
        _require(type(evidence) is SourceEvidence
                 and (baseline is None or type(baseline) is BaselineObservation))
        _require(redactor is None or type(redactor) is Redactor)
        if evidence.status != "VERIFIED":
            return result("UNKNOWN", "SOURCE_UNRESOLVED")
        root = Path(repo_root).resolve(strict=True)
        if Path(_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve() != root:
            return result("UNKNOWN", "REPOSITORY_UNAVAILABLE")
        configuration = _git(root, "config", "--includes", "--null", "--list").lower().split(b"\0")
        if any(item.startswith(b"extensions.partialclone\n") or
               item.split(b"\n", 1)[0].endswith(b".promisor") for item in configuration):
            # The evidence verifier also reads objects. Reject promisor repos
            # before invoking it so missing objects can never trigger lazy fetch.
            return result("UNKNOWN", "PARTIAL_CLONE_UNSUPPORTED")
        if _git(root, "rev-parse", "--is-shallow-repository").strip() != b"false":
            return result("UNKNOWN", "SHALLOW_HISTORY")
        head = _resolve(root, head_ref)
        base = _resolve(root, base_ref)
        bases = _git(root, "merge-base", "--all", base, head).decode("ascii").splitlines()
        if len(bases) != 1:
            return result("UNKNOWN", "AMBIGUOUS_MERGE_BASE")
        merge_base = bases[0]
        claimed = evidence.location
        if claimed.source_sha != head:
            return result("UNKNOWN", "SOURCE_COMMIT_MISMATCH")
        verified = verify_source(root, claimed.repository, head, claimed.path, claimed.region,
                                 expected_before=evidence.before, redactor=redactor)
        if verified.status != "VERIFIED":
            return result("UNKNOWN", "SOURCE_UNRESOLVED")
        location = verified.location
        old_tree, new_tree = _tree(root, merge_base), _tree(root, head)
        raw_head = _blob(root, new_tree[location.path])
        new_text = raw_head.decode("utf-8")
        selected = _selected(new_text, location.region)
        fingerprint = hashlib.sha256(json.dumps(["devsift-source-v1", rule_id, selected],
                                                ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        if not selected:
            return result("UNKNOWN", "EMPTY_SOURCE_REGION")
        if location.path not in old_tree:
            if old_tree.keys() - new_tree.keys():
                return result("UNKNOWN", "POSSIBLE_RENAME")
            total = 0
            for entry in old_tree.values():
                raw_old = _blob(root, entry)
                total += len(raw_old)
                if total > 5_000_000:
                    return result("UNKNOWN", "COMPARISON_LIMIT")
                if selected.encode("utf-8") in raw_old:
                    return result("UNKNOWN", "POSSIBLE_COPY_OR_MOVE")
            return result("NEW", "PROVEN_NEW_PATH_AND_CONTENT")
        raw_old = _blob(root, old_tree[location.path])
        if raw_old == raw_head:
            mapped = location.region
            lifecycle = "LEGACY_UNCHANGED"
        else:
            old_text = raw_old.decode("utf-8")
            if len(_lines(old_text)) > 5000 or len(_lines(new_text)) > 5000:
                return result("UNKNOWN", "COMPARISON_LIMIT")
            mapped = _unique_mapping(old_text, new_text, location.region)
            lifecycle = "MODIFIED_PREEXISTING"
        if mapped is not None:
            old_source = verify_source(root, location.repository, merge_base, location.path,
                                       mapped, redactor=redactor)
            if old_source.status == "VERIFIED":
                return result(lifecycle, "EXACT_IMMUTABLE_SOURCE_MAPPING", old_source.location)
            return result("UNKNOWN", "BASE_SOURCE_UNRESOLVED")
        if baseline is None or not baseline.complete:
            return result("UNKNOWN", "BASELINE_ANALYSIS_REQUIRED")
        if (baseline.rule_id != rule_id or baseline.source_sha != merge_base
                or baseline.path != location.path):
            return result("UNKNOWN", "BASELINE_SCOPE_MISMATCH")
        for finding in baseline.findings:
            if (finding.status != "VERIFIED" or finding.location.source_sha != merge_base
                    or finding.location.path != location.path):
                return result("UNKNOWN", "BASELINE_SOURCE_UNRESOLVED")
            checked = verify_source(root, location.repository, merge_base, location.path,
                                    finding.location.region, expected_before=finding.before, redactor=redactor)
            if checked.status != "VERIFIED":
                return result("UNKNOWN", "BASELINE_SOURCE_UNRESOLVED")
        if baseline.findings:
            return result("UNKNOWN", "EXISTING_RULE_ORIGIN_UNRESOLVED")
        return result("MODIFIED_INTRODUCED", "COMPLETE_BASELINE_RULE_ABSENT")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, subprocess.SubprocessError):
        return result("UNKNOWN", "PROVENANCE_UNAVAILABLE")
