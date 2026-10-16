"""Read-only provider discovery; PATH metadata never authorizes execution."""
from dataclasses import replace
import os
import shutil
import sys

from .adapters import LANGUAGES
from .native_host import probe_tool
from .native_manifest import load_manifest
from .output import result
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
}


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


def run_doctor(*, native_manifest=None, native_manifest_digest=None, search_path=None):
    """Return the standard command envelope; never discovers/executes project hooks.

    Without both explicit native trust inputs, execute no external process. A valid
    pair authorizes hash-checked protocol probes through the existing native host.
    Host PATH detection is advisory metadata, not trusted provider availability.
    """
    supported = sys.version_info >= (3, 12)
    runtime = {'name': 'python', 'version': '.'.join(map(str, sys.version_info[:3])),
               'supported': supported, 'minimum_version': '3.12',
               'action': '' if supported else 'Run DevSift with an approved Python 3.12 or newer interpreter; doctor does not install one.'}
    errors = []
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
            probe = probe_tool(replace(original, process=process), redactor=redactor)
            available, reason = probe.available, probe.reason
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
            'host_tools': _host_tools(search_path), 'native_configuration': configuration,
            'native_tools': native_tools, 'providers': providers,
            'capabilities': {'command_parser': True, 'read_only': True, 'inventory': True,
                'git_provenance': True, 'analyzers': all_available, 'reports': False, 'case_prompts': False},
            'analysis_performed': False,
            'limitations': ['PATH metadata and versions are unverified and advisory; no PATH candidate is executed.',
                'Successful native probes verify configured identity/version only, not semantic rule coverage or source quality.',
                'Explicit native configuration trusts executable code; hashes and the process runner are not an OS sandbox.']}
    return redactor.redact(result('doctor', complete=supported and all_available, data=data, errors=errors))
