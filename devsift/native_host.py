"""Pinned trusted tool protocol; parser positions are not immutable source proof."""
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re

from .adapters import AdapterCapability, LANGUAGES
from .evidence import Region, SourceEvidence, verify_source
from .inventory import SourceTarget
from .process_runner import ProcessSpec, run_process
from .redaction import Redactor
from .registry import RULES
from .scanner import AdapterOutcome, ScanFinding, _snapshot_matches_commit


class NativeProtocolError(ValueError):
    """Constant errors never include tool output, source, arguments or paths."""


def _require(condition):
    if not condition:
        raise NativeProtocolError("invalid native tool contract") from None


def file_digest(path):
    """SHA256 for explicitly trusted local setup artifacts, not authentication."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        total = 0
        while chunk := stream.read(65536):
            total += len(chunk)
            _require(total <= 512_000_000)
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    tool_version: str
    languages: tuple[str, ...]
    process: ProcessSpec = field(repr=False)
    executable_digest: str = field(repr=False)
    artifacts: tuple[tuple[str, str], ...] = field(repr=False)
    engine_versions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        _require(type(self.tool_id) is str and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", self.tool_id) is not None)
        _require(type(self.tool_version) is str and re.fullmatch(r"[A-Za-z0-9_.+-]{1,128}", self.tool_version) is not None)
        _require(type(self.process) is ProcessSpec and _digest(self.executable_digest))
        _require(type(self.languages) is tuple and bool(self.languages)
                 and all(type(item) is str and item in LANGUAGES for item in self.languages)
                 and len(set(self.languages)) == len(self.languages))
        _require(type(self.artifacts) is tuple and 0 < len(self.artifacts) <= 128)
        paths = []
        for pair in self.artifacts:
            _require(type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str
                     and Path(pair[0]).is_absolute() and _digest(pair[1]))
            paths.append(str(Path(pair[0]).resolve()))
        _require(len(set(paths)) == len(paths))
        _require(type(self.engine_versions) is tuple and len(self.engine_versions) <= 16)
        keys = []
        for pair in self.engine_versions:
            _require(type(pair) is tuple and len(pair) == 2
                     and all(type(item) is str and 0 < len(item) <= 128 for item in pair)
                     and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", pair[0]) is not None)
            keys.append(pair[0])
        _require(len(set(keys)) == len(keys))


@dataclass(frozen=True)
class ProbeResult:
    available: bool
    reason: str


@dataclass(frozen=True)
class NativeDiagnostic:
    rule_id: str
    region: Region


@dataclass(frozen=True)
class NativeReport:
    complete: bool
    diagnostics: tuple[NativeDiagnostic, ...] = ()
    reason: str = "ANALYSIS_FAILED"
    metadata: tuple[tuple[str, str | int], ...] = ()


def _json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            _require(key not in result)
            result[key] = value
        return result
    def invalid(_value):
        raise NativeProtocolError("invalid native tool contract")
    _require(type(text) is str and len(text) <= 2_000_000)
    return json.loads(text, object_pairs_hook=unique, parse_constant=invalid)


def _integrity(tool):
    try:
        return (file_digest(tool.process.executable) == tool.executable_digest
                and all(file_digest(path) == digest for path, digest in tool.artifacts))
    except (OSError, ValueError, RuntimeError):
        return False


def probe_tool(tool, *, redactor=None):
    _require(type(tool) is ToolDefinition)
    if not _integrity(tool):
        return ProbeResult(False, "ARTIFACT_UNAVAILABLE_OR_CHANGED")
    executed = run_process(replace(tool.process, argv=tool.process.argv + ("--probe",)), redactor=redactor)
    if executed.status != "completed" or executed.exit_code != 0:
        return ProbeResult(False, "PROBE_UNAVAILABLE")
    try:
        data = _json(executed.stdout)
        _require(type(data) is dict and set(data) == {
            "protocol_version", "tool_id", "tool_version", "languages", "engine_versions"})
        _require(data["protocol_version"] == "1" and data["tool_id"] == tool.tool_id
                 and data["tool_version"] == tool.tool_version
                 and type(data["languages"]) is list and data["languages"] == list(tool.languages)
                 and type(data["engine_versions"]) is dict
                 and data["engine_versions"] == dict(tool.engine_versions))
        return ProbeResult(True, "READY")
    except (ValueError, TypeError, RecursionError):
        return ProbeResult(False, "PROBE_PROTOCOL_OR_VERSION_MISMATCH")


def source_offsets(text, region):
    """Validate one-based code-point coordinates against original Git LF lines."""
    _require(type(text) is str and type(region) is Region)
    parts = text.split("\n")
    lines = [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    _require(region.end_line <= len(lines))
    def body(line):
        return line[:-1].removesuffix("\r") if line.endswith("\n") else line
    _require(region.start_column <= len(body(lines[region.start_line - 1])) + 1
             and region.end_column <= len(body(lines[region.end_line - 1])) + 1)
    return (sum(map(len, lines[:region.start_line - 1])) + region.start_column - 1,
            sum(map(len, lines[:region.end_line - 1])) + region.end_column - 1)


def normalize_report(data, tool, text):
    _require(type(data) is dict and set(data) == {
        "protocol_version", "tool_id", "tool_version", "complete", "diagnostics", "reason", "metadata"})
    _require(data["protocol_version"] == "1" and data["tool_id"] == tool.tool_id
             and data["tool_version"] == tool.tool_version and type(data["complete"]) is bool
             and type(data["diagnostics"]) is list and len(data["diagnostics"]) <= 1000
             and type(data["reason"]) is str and data["reason"] in {
                 "COMPLETED", "PARSE_ERROR", "UNSUPPORTED_DIALECT", "ANALYSIS_FAILED", "UNSUPPORTED_SOURCE"})
    _require(not data["complete"] or data["reason"] == "COMPLETED")
    diagnostics, seen = [], set()
    for item in data["diagnostics"]:
        _require(type(item) is dict and set(item) == {"rule_id", "region"}
                 and type(item["rule_id"]) is str and item["rule_id"] in RULES)
        region = Region.from_dict(item["region"])
        source_offsets(text, region)
        identity = (item["rule_id"], region)
        _require(identity not in seen)
        seen.add(identity)
        diagnostics.append(NativeDiagnostic(*identity))
    metadata = data["metadata"]
    _require(type(metadata) is dict and metadata.keys() <= {
        "dialect", "unqualified_references", "ddl_statements"})
    for key, value in metadata.items():
        if key == "dialect":
            _require(type(value) is str and value in {"tsql150", "tsql160"})
        else:
            _require(type(value) is int and 0 <= value <= 1_000_000)
    diagnostics.sort(key=lambda item: (item.region.start_line, item.region.start_column,
                                        item.region.end_line, item.region.end_column, item.rule_id))
    return NativeReport(data["complete"], tuple(diagnostics), data["reason"], tuple(sorted(metadata.items())))


def analyze_snapshot(tool, target, *, dialect=None, redactor=None):
    _require(type(tool) is ToolDefinition and type(target) is SourceTarget)
    if target.status != "ready" or target.language not in tool.languages or not _integrity(tool):
        return NativeReport(False, reason="UNSUPPORTED_SOURCE")
    try:
        text = target.content.decode("utf-8")
        _require(dialect is None or dialect in {"tsql150", "tsql160"})
        payload = json.dumps({"protocol_version": "1", "path": target.path,
                              "language": target.language, "source": text, "dialect": dialect},
                             ensure_ascii=False).encode("utf-8")
        executed = run_process(replace(tool.process, argv=tool.process.argv + ("--analyze",)),
                               stdin=payload, redactor=redactor)
        if executed.status != "completed" or executed.exit_code != 0:
            return NativeReport(False)
        return normalize_report(_json(executed.stdout), tool, text)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        return NativeReport(False)


class NativeAdapter:
    """Trusted configured tool; default attribution is UNKNOWN, never guessed NEW."""

    def __init__(self, tool, *, repo_root=None, source_sha=None, repository="local",
                 dialect=None, redactor=None):
        _require(type(tool) is ToolDefinition)
        _require(redactor is None or type(redactor) is Redactor)
        self.tool, self.repo_root, self.source_sha = tool, repo_root, source_sha
        self.repository, self.dialect = repository, dialect
        self.redactor = redactor or Redactor()
        self.probe = probe_tool(tool, redactor=self.redactor)
        self.capability = AdapterCapability(tool.tool_id, tool.tool_version, tool.languages, self.probe.available)

    def analyze(self, target):
        if not self.probe.available:
            return AdapterOutcome(False)
        report = analyze_snapshot(self.tool, target, dialect=self.dialect, redactor=self.redactor)
        findings = []
        for diagnostic in report.diagnostics:
            source = SourceEvidence()
            if self.repo_root is not None and self.source_sha is not None:
                try:
                    source = verify_source(self.repo_root, self.repository, self.source_sha,
                                           target.path, diagnostic.region, redactor=self.redactor)
                    if not _snapshot_matches_commit(self.repo_root, source, target.content):
                        source = SourceEvidence(reason="SOURCE_MISMATCH")
                except (OSError, ValueError, TypeError):
                    source = SourceEvidence()
            identity = json.dumps([self.tool.tool_id, diagnostic.rule_id, target.path,
                                   diagnostic.region.to_dict()], sort_keys=True).encode()
            case = "NATIVE-" + hashlib.sha256(identity).hexdigest()[:24]
            findings.append(ScanFinding(case, diagnostic.rule_id, source,
                                         RULES[diagnostic.rule_id].title))
        return AdapterOutcome(report.complete, tuple(findings))
