"""Trusted adapter execution over immutable snapshots with conservative gating."""
from dataclasses import dataclass, field
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
from typing import Protocol

from .git_runtime import git_executable
from .adapters import AdapterCapability, negotiate
from .evidence import SourceEvidence, requires_source_mask, verify_source
from .inventory import Inventory, SourceTarget, inventory, iter_inventory
from .output import result
from .policy import decide, resolve_policy
from .redaction import Redactor
from .registry import RULES

_LIFECYCLES = frozenset({'NEW', 'MODIFIED_INTRODUCED', 'MODIFIED_PREEXISTING',
                         'LEGACY_UNCHANGED', 'UNKNOWN'})


@dataclass(frozen=True)
class ScanFinding:
    case_id: str
    rule_id: str
    source: SourceEvidence = field(repr=False)
    message: str = field(default='', repr=False)
    lifecycle_class: str = 'UNKNOWN'

    def __post_init__(self):
        if (type(self.case_id) is not str
                or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', self.case_id) is None
                or type(self.rule_id) is not str or self.rule_id not in RULES
                or type(self.source) is not SourceEvidence
                or type(self.message) is not str or len(self.message) > 20_000
                or type(self.lifecycle_class) is not str or self.lifecycle_class not in _LIFECYCLES):
            raise ValueError('Invalid scan finding contract')


@dataclass(frozen=True)
class AdapterOutcome:
    complete: bool
    findings: tuple[ScanFinding, ...] = ()

    def __post_init__(self):
        if (type(self.complete) is not bool or type(self.findings) is not tuple
                or any(type(finding) is not ScanFinding for finding in self.findings)):
            raise ValueError('Outcome requires explicit boolean completeness and immutable findings')


class Adapter(Protocol):
    capability: AdapterCapability

    def analyze(self, target: SourceTarget) -> AdapterOutcome:
        """Trusted code only: immutable inputs do not sandbox Python callbacks."""
        ...


class _Discard(io.TextIOBase):
    """Drop accidental Python adapter logs without storing source-bearing data."""

    def write(self, value):
        return len(value)


def _snapshot_matches_commit(root, source, content):
    """Compare the entire raw snapshot's Git blob ID, never a masked excerpt."""
    if source.status != 'VERIFIED' or source.location is None:
        return False
    location = source.location
    environment = dict(os.environ, GIT_NO_REPLACE_OBJECTS='1', GIT_LITERAL_PATHSPECS='1',
                       GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0', GIT_NO_LAZY_FETCH='1')
    try:
        process = subprocess.run([git_executable(root), '-C', str(root), 'ls-tree', '-z', location.source_sha,
                                  '--', location.path], capture_output=True, timeout=10, env=environment)
        if process.returncode:
            return False
        entries = process.stdout.split(b'\0')
        if len(entries) != 2 or not entries[0]:
            return False
        metadata, path = entries[0].split(b'\t', 1)
        mode, kind, blob = metadata.split(b' ')
        if (mode not in (b'100644', b'100755') or kind != b'blob'
                or path.decode('utf-8') != location.path):
            return False
        payload = b'blob ' + str(len(content)).encode('ascii') + b'\0' + content
        digest = (hashlib.sha1(payload, usedforsecurity=False).hexdigest() if len(blob) == 40
                  else hashlib.sha256(payload).hexdigest() if len(blob) == 64 else None)
        return digest == blob.decode('ascii')
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        return False


def _source(root, target, finding, redactor):
    claimed = finding.source
    if (claimed.status != 'VERIFIED' or claimed.location is None
            or claimed.location.path != target.path):
        return SourceEvidence(reason='SOURCE_NOT_VERIFIED')
    location = claimed.location
    verified = verify_source(root, location.repository, location.source_sha,
                             location.path, location.region, redactor=redactor,
                             sensitive=requires_source_mask(finding.rule_id, claimed))
    if not _snapshot_matches_commit(root, verified, target.content):
        return SourceEvidence(reason='SOURCE_MISMATCH')
    return verified


def _scan_snapshot(root: str | Path, candidates=None, *, adapters: tuple[Adapter, ...] = (),
                   policy=None, redactor: Redactor | None = None, snapshot=None,
                   max_bytes=4 * 1024 * 1024) -> dict:
    """Execute one selected trusted adapter per eligible target; return JSON data.

    Lifecycle values are trusted upstream attribution, never inferred from a
    touched file. Findings default UNKNOWN. Native tools require explicit configuration.
    Invalid configuration, failed tools, unresolved evidence and partial work all
    keep the final result incomplete, even when other findings block.
    """
    if redactor is not None and type(redactor) is not Redactor:
        raise ValueError('redactor must be a Redactor')
    redactor = redactor or Redactor()
    errors, findings, public_targets = [], [], []
    enforced = 0
    complete = True
    seen_cases = set()
    counts = {name: 0 for name in ('executed', 'skipped', 'unavailable', 'incomplete')}

    def error(code):
        # Errors describe categories; individual outcomes remain in targets and
        # counts. Repeating one missing-provider error per file can otherwise
        # exhaust the bounded report model before any coverage is presented.
        if not any(item['code'] == code for item in errors):
            errors.append({'code': code, 'message': 'Scan work is incomplete; inspect declared capabilities and source evidence.'})

    try:
        resolved = resolve_policy(policy)
        if type(adapters) is not tuple:
            raise ValueError('Invalid adapter collection')
        bindings = {}
        for adapter in adapters:
            capability = adapter.capability
            if (type(capability) is not AdapterCapability or not callable(adapter.analyze)
                    or capability.adapter_id in bindings):
                raise ValueError('Invalid adapter contract')
            bindings[capability.adapter_id] = (capability, adapter)
        capabilities = tuple(pair[0] for _, pair in sorted(bindings.items()))
        if snapshot is None:
            snapshot = inventory(root, candidates)
    except Exception:
        return result('scan', complete=False,
                      errors=[{'code': 'INVALID_SCAN_INPUT', 'message': 'Invalid scan input or configuration.'}],
                      data={'targets': [], 'counts': counts})

    complete = snapshot.complete
    if not any(cap.available for cap in capabilities):
        complete = False
        error('NO_AVAILABLE_ANALYZER')

    for target in snapshot.targets:
        decision = negotiate(target, capabilities)
        public = {'path': target.path, 'status': target.status, 'language': target.language,
                  'byte_count': None if target.content is None else len(target.content),
                  'execution_status': decision.status, 'adapter_id': decision.adapter_id,
                  'adapter_version': decision.version}
        public_targets.append(public)
        if decision.status != 'supported':
            counts[decision.status] += 1
            if decision.status != 'skipped':
                complete = False
                error('ANALYZER_UNAVAILABLE' if decision.status == 'unavailable' else 'SOURCE_INCOMPLETE')
            continue
        adapter = bindings[decision.adapter_id][1]
        try:
            with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
                outcome = adapter.analyze(target)
            if type(outcome) is not AdapterOutcome:
                raise ValueError('Invalid outcome contract')
            # Re-run value checks even for a frozen object forged by a caller.
            AdapterOutcome(outcome.complete, outcome.findings)
            current = tuple(iter_inventory(root, (target.path,), max_bytes=max_bytes))
            if (len(current) != 1 or current[0].status != 'ready'
                    or current[0].content != target.content):
                raise ValueError('Source changed during adapter execution')
            evaluated = []
            for finding in outcome.findings:
                ScanFinding(finding.case_id, finding.rule_id, finding.source,
                            finding.message, finding.lifecycle_class)
                source = _source(root, target, finding, redactor)
                policy_decision = decide(finding.rule_id, finding.lifecycle_class,
                                         source_verified=source.status == 'VERIFIED', policy=resolved)
                evaluated.append((finding, source, policy_decision))
        except Exception:
            complete = False
            public['execution_status'] = 'incomplete'
            counts['incomplete'] += 1
            error('ADAPTER_FAILED')
            continue
        counts['executed'] += 1
        target_incomplete = not outcome.complete
        if not outcome.complete:
            complete = False
            error('ADAPTER_INCOMPLETE')
        for finding, source, policy_decision in evaluated:
            if finding.case_id in seen_cases:
                complete = False
                target_incomplete = True
                error('DUPLICATE_CASE_ID')
                continue
            seen_cases.add(finding.case_id)
            if policy_decision.enforcement == 'incomplete':
                complete = False
                target_incomplete = True
                error('FINDING_UNRESOLVED')
            if policy_decision.enforcement == 'block':
                enforced += 1
            findings.append({'case_id': finding.case_id, 'rule_id': finding.rule_id,
                             'message': finding.message, 'path': target.path,
                             'source': source.to_dict(), 'severity': policy_decision.severity.value,
                             'lifecycle_class': policy_decision.lifecycle_class,
                             'enforcement': policy_decision.enforcement,
                             'security_escalation': policy_decision.security_escalation})
        public['execution_status'] = 'incomplete' if target_incomplete else 'executed'
        if target_incomplete:
            counts['incomplete'] += 1

    findings.sort(key=lambda finding: (finding['path'], finding['case_id'], finding['rule_id']))
    record = result('scan', complete=complete, enforced_count=enforced, findings=findings,
                    errors=errors, data={'mode': snapshot.mode, 'targets': public_targets, 'counts': counts})
    try:
        # Mask untrusted values, preserving the protocol's fixed keys/statuses.
        # Fresh source evidence already used this redactor in full source context.
        for target in public_targets:
            for key in ('path', 'adapter_id', 'adapter_version'):
                if target[key] is not None:
                    target[key] = redactor.text(target[key])
        for finding in findings:
            for key in ('case_id', 'message', 'path'):
                finding[key] = redactor.text(finding[key])
        # Inventory size is not the size of an untrusted object. Each generated
        # target/finding is independently bounded and masked; never impose a
        # cumulative secret-processing budget on the whole repository.
        masker = Redactor()
        safe = masker.redact({**record, 'findings': [],
                              'data': {**record['data'], 'targets': []}})
        safe['data']['targets'] = [masker.redact(target) for target in public_targets]
        safe['findings'] = [masker.redact(finding) for finding in findings]
        return safe
    except Exception:
        return result('scan', complete=False,
                      errors=[{'code': 'REDACTION_FAILED', 'message': 'Scan output could not be safely serialized.'}])


def scan(root: str | Path, candidates=None, *, adapters: tuple[Adapter, ...] = (),
         policy=None, redactor: Redactor | None = None) -> dict:
    """Compatibility aggregate scan over an immutable repository snapshot."""
    return _scan_snapshot(root, candidates, adapters=adapters, policy=policy, redactor=redactor)


def iter_scan(root: str | Path, candidates=None, *, adapters: tuple[Adapter, ...] = (),
              policy=None, redactor: Redactor | None = None, max_bytes=None):
    """Yield one redacted envelope per target without retaining repository content.

    Duplicate case IDs across targets must be checked by the persistent consumer.
    Each target is snapshotted once before analysis and reread only to detect
    mutation during execution. Closing this iterator closes the inventory.
    """
    mode = 'all' if candidates is None else 'incremental'
    targets = iter_inventory(root, candidates, max_bytes=max_bytes)
    emitted = False
    try:
        for target in targets:
            emitted = True
            yield _scan_snapshot(root, adapters=adapters, policy=policy, redactor=redactor,
                                 snapshot=Inventory(mode, (target,)), max_bytes=max_bytes)
            del target
        if not emitted:
            yield _scan_snapshot(root, adapters=adapters, policy=policy, redactor=redactor,
                                 snapshot=Inventory(mode, ()), max_bytes=max_bytes)
    except (ValueError, OSError):
        yield result('scan', complete=False, errors=[{
            'code': 'INVALID_SCAN_INPUT', 'message': 'Invalid scan input or configuration.'}],
            data={'mode': mode, 'targets': [], 'counts': {
                name: 0 for name in ('executed', 'skipped', 'unavailable', 'incomplete')}})
    finally:
        targets.close()
