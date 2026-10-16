"""Fresh bounded security escalation, independent of quality lifecycle gates."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

from .adapters import AdapterCapability, LANGUAGES
from .evidence import SourceEvidence
from .git_runtime import git_executable
from .inventory import inventory
from .native_host import NativeAdapter, ToolDefinition
from .policy import resolve_policy
from .redaction import Redactor
from .registry import RULES, Severity
from .scanner import AdapterOutcome, scan
from .security_adapter import SecurityAdapter

_SEAL = object()


def _require(condition):
    if not condition:
        raise ValueError("invalid security gate input") from None


def _paths(value, *, allow_empty=False):
    _require(type(value) is tuple and (allow_empty or bool(value)) and len(value) <= 256)
    for path in value:
        _require(type(path) is str and 0 < len(path) <= 1024)
        _require(not any(ord(char) < 32 or ord(char) == 127 or char in "\\:" for char in path))
        _require(all(part not in ("", ".", "..", ".git") for part in path.split("/")))
        _require(Redactor().text(path) == path)
    _require(len(set(value)) == len(value))
    return tuple(sorted(value))


def _git(root, *args):
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1",
                       GIT_NO_LAZY_FETCH="1", GIT_LITERAL_PATHSPECS="1", GIT_TERMINAL_PROMPT="0")
    process = subprocess.run([git_executable(root), "--no-optional-locks", "-c", "core.fsmonitor=false",
                              "-C", str(root), *args], capture_output=True, timeout=10, env=environment)
    _require(process.returncode == 0 and len(process.stdout) <= 2_000_000)
    return process.stdout


def _head(root):
    sha = _git(root, "rev-parse", "--verify", "--end-of-options", "HEAD^{commit}").decode("ascii").strip()
    _require(re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", sha) is not None)
    return sha


def _matches(root, sha, target):
    if target.status != "ready" or type(target.content) is not bytes:
        return False
    entries = _git(root, "ls-tree", "-z", sha, "--", target.path).split(b"\0")
    if len(entries) != 2 or not entries[0]:
        return False
    metadata, path = entries[0].split(b"\t", 1)
    mode, kind, oid = metadata.split(b" ")
    if mode not in (b"100644", b"100755") or kind != b"blob" or path.decode("utf-8") != target.path:
        return False
    payload = b"blob " + str(len(target.content)).encode("ascii") + b"\0" + target.content
    digest = (hashlib.sha1(payload, usedforsecurity=False).hexdigest() if len(oid) == 40 else
              hashlib.sha256(payload).hexdigest() if len(oid) == 64 else None)
    return digest == oid.decode("ascii")


class _BoundAdapter:
    """Ensure scanner actually analyzes the exact initially proved snapshots."""
    def __init__(self, delegate, expected):
        self.capability, self._delegate, self._expected = delegate.capability, delegate, expected

    def analyze(self, target):
        if target.path not in self._expected or target.content != self._expected[target.path]:
            return AdapterOutcome(False)
        return self._delegate.analyze(target)


@dataclass(frozen=True, init=False)
class SecurityGateResult:
    complete: bool
    requires_security_review: bool
    source_sha: str | None
    reasons: tuple[str, ...]
    _json: str = field(repr=False)

    def __init__(self, token=None, **values):
        _require(token is _SEAL and set(values) == set(self.__dataclass_fields__))
        for key, value in values.items():
            object.__setattr__(self, key, value)

    @property
    def status(self):
        return ("incomplete" if not self.complete else "security_review" if self.requires_security_review
                else "no_detected_critical_in_declared_scope")

    @property
    def write_authorized(self):
        return False

    @property
    def execution_authorized(self):
        return False

    @property
    def rotation_authorized(self):
        return False

    @property
    def publication_authorized(self):
        return False

    def to_dict(self):
        return json.loads(self._json)


def run_security_gate(repo_root, *, paths=None, policy=None, tools=(), config_paths=(), redactor=None):
    """Run accepted detectors afresh over an explicit bounded Git-backed scope.

    ToolDefinitions are explicit trusted executable configuration, not permission
    for remediation. No saved report, baseline, waiver or approval input exists.
    """
    sha = None
    reasons, findings, selected, tool_versions = [], [], (), []
    public_redactor = redactor if type(redactor) is Redactor else Redactor()

    def finish():
        unique = tuple(dict.fromkeys(reasons))
        complete = not unique
        review = any(item["requires_security_review"] for item in findings)
        status = "incomplete" if not complete else "security_review" if review else "no_detected_critical_in_declared_scope"
        payload = {"schema_version": "1", "status": status, "complete": complete,
                   "requires_security_review": review, "source_sha": sha, "reasons": list(unique),
                   "paths": [public_redactor.text(path) for path in selected], "findings": findings,
                   "coverage": {"builtin_version": "1.1.0", "credential_shapes_languages": sorted(LANGUAGES),
                                "builtin_security_context_languages": ["python"], "explicit_tools": tool_versions},
                   "credential_liveness": "unknown", "exploitability": "unknown", "business_impact": "unknown",
                   "quality_gate_complete": False, "write_authorized": False, "execution_authorized": False,
                   "rotation_authorized": False, "publication_authorized": False}
        return SecurityGateResult(_SEAL, complete=complete, requires_security_review=review,
                                  source_sha=sha, reasons=unique, _json=json.dumps(payload, sort_keys=True))

    try:
        if paths is None:
            reasons.append("SCOPE_REQUIRED")
            return finish()
        selected = _paths(paths)
        configured = _paths(config_paths, allow_empty=True)
        _require(set(configured) <= set(selected))
        _require(redactor is None or type(redactor) is Redactor)
        redactor = redactor or Redactor()
        resolved = resolve_policy(policy)
        _require(type(tools) is tuple and len(tools) <= 6 and all(type(tool) is ToolDefinition for tool in tools))
        covered = set()
        for tool in tools:
            _require(not covered.intersection(tool.languages))
            covered.update(tool.languages)
        origin = Path(repo_root)
        _require(not origin.is_symlink() and not origin.is_junction())
        root = origin.resolve(strict=True)
        _require(Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root)
        configuration = _git(root, "config", "--includes", "--null", "--list").lower().split(b"\0")
        _require(not any(item.startswith(b"extensions.partialclone\n") or
                         item.split(b"\n", 1)[0].endswith(b".promisor") for item in configuration))
        _require(_git(root, "rev-parse", "--is-shallow-repository").strip() == b"false")
        sha = _head(root)
        initial = inventory(root, selected, max_bytes=2_000_000)
        _require(len(initial.targets) == len(selected) and
                 sum(len(target.content or b"") for target in initial.targets) <= 2_000_000)
        if not initial.complete or not all(_matches(root, sha, target) for target in initial.targets):
            reasons.append("SNAPSHOT_UNVERIFIED")
        expected = {target.path: target.content for target in initial.targets}
        adapters = []
        for tool in tools:
            delegate = NativeAdapter(tool, repo_root=root, source_sha=sha, redactor=redactor)
            if not delegate.probe.available:
                reasons.append("CONFIGURED_PROVIDER_UNAVAILABLE")
            adapters.append(SecurityAdapter(delegate, repo_root=root, source_sha=sha,
                                             config_paths=configured, redactor=redactor))
            tool_versions.append({"tool_id": redactor.text(tool.tool_id), "version": redactor.text(tool.tool_version)})
        missing = tuple(sorted(LANGUAGES - covered))
        if missing:
            builtin = SecurityAdapter(repo_root=root, source_sha=sha, config_paths=configured, redactor=redactor)
            capability = builtin.capability
            builtin.capability = AdapterCapability(capability.adapter_id, capability.version, missing, True)
            adapters.append(builtin)
        record = scan(root, selected, adapters=tuple(_BoundAdapter(adapter, expected) for adapter in adapters),
                      policy=resolved, redactor=redactor)
        if record.get("data", {}).get("counts", {}).get("executed") != len(selected):
            reasons.append("ANALYSIS_UNAVAILABLE")
        for error in record.get("errors", ()):
            # UNKNOWN quality provenance is not security execution failure when
            # every detector observation independently has actual source proof.
            if error.get("code") != "FINDING_UNRESOLVED":
                reasons.append("ANALYSIS_INCOMPLETE")
        for finding in record.get("findings", ()):
            rule = RULES[finding["rule_id"]]
            source = SourceEvidence.from_dict(finding["source"], repo_root=root, redactor=redactor)
            verified = (source.status == "VERIFIED" and source.location.source_sha == sha
                        and source.location.path in selected
                        and redactor.text(source.location.path) == finding["path"])
            if not verified:
                reasons.append("FINDING_SOURCE_UNRESOLVED")
            if not rule.security:
                continue
            critical = rule.severity == Severity.CRITICAL or finding["severity"] == "Critical"
            display = source.to_dict()
            if display["location"] is not None:
                for key in ("repository", "path", "symbol"):
                    if display["location"][key] is not None:
                        display["location"][key] = redactor.text(display["location"][key])
            findings.append({"case_id": redactor.text(finding["case_id"]), "rule_id": rule.id,
                             "catalog_severity": rule.severity.value, "resolved_severity": finding["severity"],
                             "path": redactor.text(finding["path"]), "source": display,
                             "lifecycle_class": "UNKNOWN", "quality_enforcement": finding["enforcement"],
                             "requires_security_review": verified and critical})
        final = inventory(root, selected, max_bytes=2_000_000)
        if (_head(root) != sha or final != initial or
                not all(_matches(root, sha, target) for target in final.targets)):
            reasons.append("SNAPSHOT_CHANGED_OR_UNVERIFIED")
    except Exception:
        # Never echo Git/native stderr, raw source, configuration or exception repr.
        reasons.append("SECURITY_GATE_UNAVAILABLE_OR_INVALID")
    return finish()
