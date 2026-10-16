"""Read-only provider discovery; PATH metadata never authorizes execution."""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import stat
import sys

from .adapters import LANGUAGES
from .native_host import probe_tool
from .native_manifest import load_manifest
from .output import result
from .policy import _invalid_constant, _unique_object, resolve_policy
from .redaction import Redactor


_SETUP = ('See docs/NATIVE-SETUP.md. Perform approved DevSift helper setup separately, '
          'review the manifest, then supply its absolute path and independently trusted SHA256; '
          'doctor never installs or builds tools.')
_HOST_TOOLS = (
    ('git', 'Git source provenance', 'Provide an approved Git installation when source provenance is required.'),
    ('dotnet', '.NET native helper runtime/setup', 'Use the approved .NET runtime/SDK for the pinned Roslyn and ScriptDom helpers.'),
    ('go', 'Go helper setup', 'Use the approved Go SDK for separate DevSift helper setup; an already-built helper does not need Go on PATH.'),
    ('node', 'Frontend helper runtime/setup', 'Use the approved Node runtime for the pinned frontend helper.'),
    ('npm', 'Frontend helper setup', 'Use the approved npm setup and locked helper dependencies separately; doctor does not install them.'),
)
_PROBE_ACTIONS = {
    'READY': '',
    'ARTIFACT_UNAVAILABLE_OR_CHANGED': 'Restore the independently reviewed pinned runtime/helper artifacts. Rebuild or update trust only as a separate approved setup operation.',
    'PROBE_UNAVAILABLE': 'Check that the approved helper can run within doctor limits (5 seconds, 32 KiB stdout, 16 KiB stderr); inspect it separately without running target-project commands.',
    'PROBE_PROTOCOL_OR_VERSION_MISMATCH': 'Use helper/runtime versions matching the reviewed manifest and native protocol v1. Do not regenerate pins automatically.',
    'DOCTOR_CONFIG_UNAVAILABLE': 'Correct the explicit root/policy/cache diagnostic failure before requesting native probes again.',
}


def _walk_metadata(path, *, missing_ok=False):
    """Inspect original components before resolving; never enumerate children."""
    if not path.is_absolute() or '..' in path.parts or len(str(path)) > 4096 or len(path.parts) > 128:
        raise ValueError('Unavailable diagnostic path')
    current = Path(path.anchor)
    parts = path.parts[1:]
    for index in range(len(parts) + 1):
        if index:
            current = current / parts[index - 1]
        try:
            info = current.lstat()
        except FileNotFoundError:
            if missing_ok:
                return None
            raise
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400):
            raise ValueError('Unavailable diagnostic path')
        if index < len(parts) and not stat.S_ISDIR(info.st_mode):
            raise ValueError('Unavailable diagnostic path')
    return info


def _diagnostic_path(origin, value, *, missing_ok=False):
    path = Path(value)
    if '..' in path.parts or (path.drive and not path.is_absolute()):
        raise ValueError('Unavailable diagnostic path')
    path = path if path.is_absolute() else origin / path
    if not path.is_relative_to(origin):
        raise ValueError('Unavailable diagnostic path')
    info = _walk_metadata(path, missing_ok=missing_ok)
    if not path.resolve(strict=False).is_relative_to(origin):
        raise ValueError('Unavailable diagnostic path')
    return path, info


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _policy_snapshot(origin, value):
    path, before = _diagnostic_path(origin, value)
    if path.suffix.lower() != '.json' or not stat.S_ISREG(before.st_mode) or before.st_size > 1048576:
        raise ValueError('Unavailable policy snapshot')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            raise ValueError('Unavailable policy snapshot')
        chunks, remaining = [], 1048577
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b''.join(chunks)
        if len(raw) > 1048576 or _identity(os.fstat(descriptor)) != _identity(opened):
            raise ValueError('Unavailable policy snapshot')
    finally:
        os.close(descriptor)
    _, after = _diagnostic_path(origin, value)
    if _identity(after) != _identity(before):
        raise ValueError('Unavailable policy snapshot')
    # Reuse load_policy's strict JSON hooks and public resolution semantics on
    # this bounded snapshot; do not reopen the path or create a temporary file.
    layer = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if type(layer) is not dict:  # resolve_policy(None) means defaults, JSON null does not.
        raise ValueError('Unavailable policy snapshot')
    return resolve_policy(layer)


def _config_cache_checks(root, policy_path, cache_path):
    config = {'status': 'default', 'reason': 'DEFAULT_IN_MEMORY', 'action': '', 'policy_schema_version': '1'}
    cache = {'status': 'not_requested', 'reason': 'NO_EXPLICIT_CACHE', 'action': ''}
    errors = []
    try:
        original = Path.cwd() if root is None else Path(root).absolute()
        info = _walk_metadata(original)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Unavailable root')
        origin = original.resolve(strict=True)
    except (OSError, ValueError, TypeError, RuntimeError):
        config.update(status='incomplete', reason='ROOT_UNAVAILABLE', policy_schema_version=None,
                      action='Use an existing stable non-link diagnostic root.')
        cache.update(status='incomplete', reason='ROOT_UNAVAILABLE', action='Use an existing stable non-link diagnostic root.')
        return config, cache, [{'code': 'DOCTOR_ROOT_UNAVAILABLE', 'message': 'Diagnostic root metadata is invalid or unavailable.'}]
    try:
        policy = resolve_policy() if policy_path is None else _policy_snapshot(origin, policy_path)
        config.update(status='default' if policy_path is None else 'valid',
                      reason='DEFAULT_IN_MEMORY' if policy_path is None else 'EXPLICIT_JSON_VALID',
                      policy_schema_version=policy['schema_version'])
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        config.update(status='incomplete', reason='POLICY_UNAVAILABLE', policy_schema_version=None,
                      action='Use an explicit readable UTF-8 JSON policy within the root, at most 1 MiB, with valid unique keys and no links/reparse components.')
        errors.append({'code': 'DOCTOR_POLICY_UNAVAILABLE', 'message': 'Explicit policy JSON is invalid, unsafe or unavailable.'})
    if cache_path is not None:
        try:
            path, info = _diagnostic_path(origin, cache_path, missing_ok=True)
            if info is None:
                cache.update(status='missing', reason='OPTIONAL_CACHE_ABSENT',
                             action='No cache exists at the explicit location. No directory was created; a cache is optional for diagnostics.')
            elif stat.S_ISDIR(info.st_mode) and os.access(path, os.R_OK | os.X_OK):
                cache.update(status='present', reason='DIRECTORY_METADATA_ONLY',
                             action='Only directory metadata/access hints were checked; child contents, total size and writability were not checked.')
            else:
                raise ValueError('Unavailable cache')
        except (OSError, ValueError, TypeError, RuntimeError):
            cache.update(status='incomplete', reason='CACHE_UNAVAILABLE',
                         action='Use an accessible non-link directory within the diagnostic root; inspect permissions separately without changing or clearing cache here.')
            errors.append({'code': 'DOCTOR_CACHE_UNAVAILABLE', 'message': 'Explicit cache metadata is invalid, unsafe or unavailable.'})
    return config, cache, errors


def _host_tools(search_path):
    path = os.environ.get('PATH', '') if search_path is None else search_path
    valid = type(path) is str and len(path) <= 32768 and '\0' not in path and len(path.split(os.pathsep)) <= 512
    records = []
    for identity, purpose, action in _HOST_TOOLS:
        try:
            detected = bool(shutil.which(identity, path=path)) if valid else False
            status = 'discovered_unverified' if detected else 'missing' if valid else 'discovery_unavailable'
        except (OSError, ValueError, TypeError):
            detected, status = False, 'discovery_unavailable'
        records.append({'tool_id': identity, 'purpose': purpose, 'detected': detected,
            'status': status, 'version': None, 'reason': 'PATH_METADATA_ONLY' if detected else
            'NOT_FOUND_ON_SEARCH_PATH' if status == 'missing' else 'PATH_METADATA_UNAVAILABLE',
            'action': action + ' PATH presence is unverified metadata; version commands are not executed.'})
    return records


def run_doctor(*, native_manifest=None, native_manifest_digest=None, search_path=None,
               root=None, policy_path=None, cache_path=None):
    """Return the standard command envelope; never discovers/executes project hooks.

    Without both explicit native trust inputs, execute no external process. A valid
    pair authorizes hash-checked protocol probes through the existing native host.
    Host PATH detection is advisory metadata, not trusted provider availability.
    """
    supported = sys.version_info >= (3, 12)
    runtime = {'name': 'python', 'version': '.'.join(map(str, sys.version_info[:3])),
               'supported': supported, 'minimum_version': '3.12',
               'action': '' if supported else 'Run DevSift with an approved Python 3.12 or newer interpreter; doctor does not install one.'}
    config_checks, cache_checks, errors = _config_cache_checks(root, policy_path, cache_path)
    checks_ok = not errors
    if not supported:
        errors.append({'code': 'PYTHON_RUNTIME_UNSUPPORTED', 'message': 'DevSift requires Python 3.12 or newer.'})
    configured = ()
    configuration = 'unconfigured'
    if native_manifest is None and native_manifest_digest is None:
        errors.append({'code': 'NATIVE_MANIFEST_UNCONFIGURED', 'message': _SETUP})
    else:
        try:
            # The entire manifest validates before the first probe; pins are preserved.
            configured = load_manifest(native_manifest, native_manifest_digest)
            configuration = 'validated'
        except (OSError, ValueError, TypeError, RuntimeError):
            configuration = 'invalid'
            errors.append({'code': 'NATIVE_MANIFEST_UNAVAILABLE',
                           'message': 'Native manifest or its independent digest is invalid or unavailable. No native probes were started.'})
    redactor = Redactor()
    native_tools, by_language = [], {}
    for entry in configured:
        original = entry.tool
        process = replace(original.process, timeout_seconds=min(original.process.timeout_seconds, 5),
            max_stdout_bytes=min(original.process.max_stdout_bytes, 32768),
            max_stderr_bytes=min(original.process.max_stderr_bytes, 16384),
            max_stdin_bytes=1)
        try:
            if checks_ok:
                probe = probe_tool(replace(original, process=process), redactor=redactor)
                available, reason = probe.available, probe.reason
            else:
                available, reason = False, 'DOCTOR_CONFIG_UNAVAILABLE'
            if reason not in _PROBE_ACTIONS:
                available, reason = False, 'PROBE_UNAVAILABLE'
        except (OSError, ValueError, TypeError, RuntimeError):
            available, reason = False, 'PROBE_UNAVAILABLE'
        item = {'adapter_id': original.tool_id, 'available': available,
                'configured_version': original.tool_version,
                'version': original.tool_version if available else None,
                'engine_versions': dict(original.engine_versions) if available else {},
                'languages': list(original.languages), 'reason': reason,
                'action': _PROBE_ACTIONS[reason], 'dialect': entry.dialect}
        native_tools.append(item)
        for language in original.languages:
            by_language[language] = item
    providers = []
    for language in sorted(LANGUAGES):
        item = by_language.get(language)
        providers.append({'language': language,
            'available': bool(item and item['available']),
            'adapter_id': item['adapter_id'] if item else None,
            'version': item['version'] if item else None,
            'engine_versions': item['engine_versions'] if item else {},
            'dialect': item['dialect'] if item and language == 'sql' else None,
            'reason': item['reason'] if item else 'NO_TRUSTED_PROVIDER',
            'action': item['action'] if item else 'No trusted provider is configured for this language. ' + _SETUP})
    all_available = bool(providers) and all(item['available'] for item in providers)
    if not all_available:
        errors.append({'code': 'NATIVE_PROVIDER_UNAVAILABLE',
                       'message': 'One or more language providers are unavailable or unverified. Empty findings do not mean a clean scan.'})
    data = {'scope': 'provider_discovery_only', 'runtime': runtime,
            'config_checks': config_checks, 'cache_checks': cache_checks,
            'host_tools': _host_tools(search_path), 'native_configuration': configuration,
            'native_tools': native_tools, 'providers': providers,
            'capabilities': {'command_parser': True, 'read_only': True, 'inventory': True,
                'git_provenance': True, 'analyzers': all_available, 'reports': False, 'case_prompts': False},
            'analysis_performed': False,
            'limitations': ['PATH metadata and versions are unverified and advisory; no PATH candidate is executed.',
                'Successful native probes verify configured identity/version only, not semantic rule coverage or source quality.',
                'Explicit native configuration trusts executable code; hashes and the process runner are not an OS sandbox.']}
    return redactor.redact(result('doctor', complete=supported and all_available and checks_ok, data=data, errors=errors))
