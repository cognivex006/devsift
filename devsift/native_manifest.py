"""External-digest-bound explicit native code authorization; no discovery/probes."""
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re

from .native_host import ToolDefinition
from .process_runner import ProcessSpec


class ManifestError(ValueError):
    """No input paths, configuration values or tool output in public errors."""


def _require(condition):
    if not condition:
        raise ManifestError('Invalid or unavailable native manifest') from None


@dataclass(frozen=True)
class ConfiguredTool:
    tool: ToolDefinition = field(repr=False)
    dialect: str | None = None


def _fields(data, expected):
    _require(type(data) is dict and set(data) == set(expected))


def _pairs(value):
    _require(type(value) is list and len(value) <= 256)
    _require(all(type(pair) is list and len(pair) == 2 and all(type(v) is str for v in pair) for pair in value))
    return tuple(tuple(pair) for pair in value)


def _decode(raw):
    def unique(pairs):
        data = {}
        for key, value in pairs:
            _require(key not in data)
            data[key] = value
        return data
    def invalid(_):
        raise ManifestError('Invalid or unavailable native manifest')
    data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid)
    _fields(data, ('schema_version', 'tools'))
    _require(data['schema_version'] == '1' and type(data['tools']) is list and 0 < len(data['tools']) <= 16)
    entries, identities, languages = [], set(), set()
    for entry in data['tools']:
        _fields(entry, ('definition', 'dialect'))
        definition = entry['definition']
        _fields(definition, ('tool_id', 'tool_version', 'languages', 'process',
                             'executable_digest', 'artifacts', 'engine_versions'))
        process = definition['process']
        _fields(process, ('executable', 'argv', 'timeout_seconds', 'max_stdout_bytes',
                          'max_stderr_bytes', 'max_stdin_bytes', 'environment'))
        _require(type(process['argv']) is list and type(definition['languages']) is list)
        specification = ProcessSpec(process['executable'], tuple(process['argv']), process['timeout_seconds'],
                                    process['max_stdout_bytes'], process['max_stderr_bytes'],
                                    process['max_stdin_bytes'], _pairs(process['environment']))
        # No hashing here: stored pins must survive the load unchanged.
        tool = ToolDefinition(definition['tool_id'], definition['tool_version'], tuple(definition['languages']),
                              specification, definition['executable_digest'], _pairs(definition['artifacts']),
                              _pairs(definition['engine_versions']))
        _require(tool.tool_id not in identities and not languages.intersection(tool.languages))
        _require(entry['dialect'] in ('tsql150', 'tsql160') if 'sql' in tool.languages
                 else entry['dialect'] is None)
        identities.add(tool.tool_id)
        languages.update(tool.languages)
        entries.append(ConfiguredTool(tool, entry['dialect']))
    return tuple(sorted(entries, key=lambda entry: entry.tool.tool_id))


def load_manifest(path, expected_digest):
    """Validate the entire trusted manifest before any native executable runs."""
    try:
        _require(type(expected_digest) is str and re.fullmatch('[0-9a-f]{64}', expected_digest) is not None)
        path = Path(path)
        _require(path.is_absolute())
        with path.open('rb') as stream:
            raw = stream.read(2_000_001)
        _require(len(raw) <= 2_000_000 and hashlib.sha256(raw).hexdigest() == expected_digest)
        return _decode(raw)
    except (OSError, ValueError, TypeError, RecursionError, RuntimeError):
        raise ManifestError('Invalid or unavailable native manifest') from None


def manifest_bytes(entries):
    """Explicit setup serialization only; returns bytes without writing/probing."""
    try:
        _require(type(entries) is tuple and all(type(entry) is ConfiguredTool for entry in entries))
        wire = {'schema_version': '1', 'tools': [
            {'definition': asdict(entry.tool), 'dialect': entry.dialect} for entry in entries]}
        raw = (json.dumps(wire, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
        _require(len(raw) <= 2_000_000)
        _decode(raw)
        return raw
    except (OSError, ValueError, TypeError, RecursionError, RuntimeError):
        raise ManifestError('Invalid or unavailable native manifest') from None
