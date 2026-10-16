"""Authoritative fresh read-only CI scans, never gate untrusted report JSON."""
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .adapters import AdapterCapability
from .cli_scan import _git, changed_candidates
from .git_changes import classify
from .native_host import NativeAdapter
from .native_manifest import load_manifest
from .output import result
from .scanner import AdapterOutcome, scan


class CiError(ValueError):
    """Constant safe configuration failure."""


@dataclass(frozen=True)
class GateConfig:
    minimum_severity: str = 'Error'
    require_security_review: bool = True

    def __post_init__(self):
        if (type(self.minimum_severity) is not str
                or self.minimum_severity not in ('Critical', 'Error')
                or type(self.require_security_review) is not bool):
            raise CiError('Invalid CI gate configuration') from None

    def policy(self):
        levels = ['Critical', 'Error']
        return {'quality_gate': {'block_on': levels[:levels.index(self.minimum_severity)+1]}}


@dataclass(frozen=True)
class CiRun:
    exit_code: int
    _scan: str = field(repr=False)
    _public: str = field(repr=False)

    def scan_record(self):
        return json.loads(self._scan)

    def to_dict(self):
        return json.loads(self._public)


class _ProvenanceAdapter:
    """Classify actual findings before the scanner computes completeness."""
    def __init__(self, delegate, root, base_ref, head, languages=None):
        self.delegate, self.root, self.base_ref, self.head = delegate, root, base_ref, head
        original = delegate.capability
        self.capability = AdapterCapability('ci-' + original.adapter_id, original.version,
                                             original.languages if languages is None else languages, original.available)

    def analyze(self, target):
        # A clean result must describe the selected immutable CI snapshot too;
        # dirty/untracked clean bytes cannot hide a finding present at HEAD.
        entries = _git(self.root, 'ls-tree', '-z', self.head, '--', target.path).split(b'\0')
        if len(entries) != 2 or not entries[0]:
            return AdapterOutcome(False)
        metadata, path = entries[0].split(b'\t', 1)
        mode, kind, blob = metadata.split(b' ')
        if mode not in (b'100644', b'100755') or kind != b'blob' or path.decode('utf-8') != target.path:
            return AdapterOutcome(False)
        payload = b'blob ' + str(len(target.content)).encode('ascii') + b'\0' + target.content
        digest = hashlib.sha1(payload, usedforsecurity=False).hexdigest() if len(blob) == 40 else hashlib.sha256(payload).hexdigest()
        if digest != blob.decode('ascii'):
            return AdapterOutcome(False)
        outcome = self.delegate.analyze(target)
        if type(outcome) is not AdapterOutcome:
            return AdapterOutcome(False)
        findings = []
        for finding in outcome.findings:
            lifecycle = 'UNKNOWN'
            if self.base_ref is not None:
                proof = classify(self.root, self.base_ref, self.head, finding.rule_id, finding.source)
                lifecycle = proof.lifecycle_class
            findings.append(replace(finding, lifecycle_class=lifecycle))
        return AdapterOutcome(outcome.complete, tuple(findings))


def _encode(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
    if len(raw) > 4_000_000:
        raise CiError('CI result exceeds output limit')
    return raw


def run_ci(root, *, native_manifest, native_manifest_digest, base_ref=None,
           all_scope=False, paths=None, security=False, config=None):
    """Execute configured analyzers now, with optional real Git source attribution.

    The base ref proves source origin only. Changed-region introduction without
    complete same-rule baseline evidence stays UNKNOWN; a touched file is never
    wholly NEW. No result file, build, install or remediation is performed.
    """
    if config is None:
        config = GateConfig()
    if type(config) is not GateConfig or type(all_scope) is not bool or type(security) is not bool:
        raise CiError('Invalid CI gate configuration') from None
    try:
        root = Path(root).resolve(strict=True)
        configured = load_manifest(native_manifest, native_manifest_digest)
        top = Path(_git(root, 'rev-parse', '--show-toplevel').decode('utf-8').strip()).resolve()
        head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()
        if top != root or re.fullmatch('(?:[0-9a-f]{40}|[0-9a-f]{64})', head) is None:
            raise CiError('Immutable source unavailable')
        if base_ref is not None:
            if type(base_ref) is not str or not base_ref or len(base_ref) > 1024 or any(ord(c)<32 for c in base_ref):
                raise CiError('Invalid base reference')
            base_ref = _git(root, 'rev-parse', '--verify', '--end-of-options', base_ref+'^{commit}').decode('ascii').strip()
        if paths is not None:
            if (type(paths) is not tuple or not paths or len(paths) > 1000
                    or any(type(path) is not str for path in paths) or all_scope):
                raise CiError('Invalid explicit scan scope')
            candidates, scope = list(paths), 'paths'
        else:
            candidates, scope = (None, 'all') if all_scope else (changed_candidates(root), 'changed')
        native = tuple(NativeAdapter(entry.tool, repo_root=root, source_sha=head,
                                     dialect=entry.dialect) for entry in configured)
        delegates = [(delegate, None) for delegate in native]
        if security:
            from .security_adapter import SecurityAdapter
            delegates = [(SecurityAdapter(delegate, repo_root=root, source_sha=head), None) for delegate in native]
            covered = {language for delegate, _ in delegates for language in delegate.capability.languages}
            if 'python' not in covered:
                standalone = SecurityAdapter(repo_root=root, source_sha=head)
                # The standalone detector covers only otherwise unregistered languages.
                original = standalone.capability
                languages = tuple(language for language in original.languages if language not in covered)
                delegates.append((standalone, languages))
        adapters = tuple(_ProvenanceAdapter(delegate, root, base_ref, head, languages) for delegate, languages in delegates)
        record = scan(root, candidates, adapters=adapters, policy=config.policy())
        if any(not delegate.probe.available for delegate in native):
            record.update(complete=False, status='incomplete', exit_code=2)
            record['errors'].append({'code': 'NATIVE_TOOL_UNAVAILABLE', 'message': 'A configured native tool is unavailable.'})
        review_required = config.require_security_review and any(
            finding['security_escalation'] for finding in record['findings'])
        public = json.loads(_encode(record))
        public['command'] = 'ci'
        if review_required and public['exit_code'] == 0:
            public.update(complete=False, status='incomplete', exit_code=2)
            public['errors'].append({'code': 'SECURITY_REVIEW_REQUIRED', 'message': 'Verified security findings require independent review.'})
        public['data'].update(scope=scope, quality_gate={'minimum_severity': config.minimum_severity,
                              'security_review_required': review_required, 'source_attribution': base_ref is not None})
        return CiRun(public['exit_code'], _encode(record), _encode(public))
    except (OSError, ValueError, TypeError, KeyError, ImportError, UnicodeError, subprocess.SubprocessError):
        failure = result('scan', complete=False, errors=[{'code': 'CI_SCAN_UNAVAILABLE',
                         'message': 'CI configuration, immutable source or configured analyzers are unavailable.'}])
        public = dict(failure, command='ci')
        return CiRun(2, _encode(failure), _encode(public))
