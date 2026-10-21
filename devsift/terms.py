"""Bounded offline third-party inventory and explicitly pinned review evidence.

Repository declarations describe inputs, never authority. Only a digest selected
by the operator can supply reviewed conclusions; even those are re-proved against
physical files. This is neither legal advice nor complete dependency discovery.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tomllib
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

from .redaction import Redactor, RedactionError

_SEAL = object()
_MAX_FILE = 2_000_000
_MAX_TOTAL = 16_000_000
_MAX_COMPONENTS = 1000
_SKIP = frozenset({'.git', '.hg', '.svn', '.aws', '.codex', '.agents',
                   'node_modules', '.venv', 'venv', 'worktrees', '__pycache__',
                   'bin', 'obj', 'dist', 'build'})
_META = frozenset({'.git', '.hg', '.svn', '.aws', '.codex', '.agents'})
_ECOSYSTEMS = frozenset({'npm', 'pypi', 'nuget', 'go', 'runtime', 'saas', 'tool'})
_KINDS = frozenset({'library', 'build', 'development', 'runtime', 'service', 'tool'})
_HEX = re.compile(r'[0-9a-f]{64}')
_QUOTED_SECRET = re.compile(r'''(?i)["']?(?:password|passwd|secret|token|api[_-]?key|authorization|credential)s?["']?\s*[:=]\s*["']([^"'\r\n]{1,4096})["']''')


class TermsError(ValueError):
    """Constant safe input failure; no repository data in exceptions."""


def _require(condition):
    if not condition:
        raise TermsError('Invalid or unavailable terms evidence') from None


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value if type(value) is bytes else _json(value).encode()).hexdigest()


def _text(value, limit=4096, multiline=False):
    _require(type(value) is str and 0 < len(value) <= limit and
             not any((ord(c) < 32 and not (multiline and c in '\n\r\t')) or ord(c) == 127 for c in value))
    return value


def _fields(value, keys):
    _require(type(value) is dict and set(value) == set(keys))


def _timestamp(value):
    _text(value, 64)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise TermsError('Invalid or unavailable terms evidence') from None
    _require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0)
    return parsed


def _physical(path):
    """Reject links and Windows reparse points in every existing ancestor."""
    path = Path(path)
    _require(path.is_absolute())
    for part in (path, *path.parents):
        if part.name:
            _safe_part(part.name)
        info = part.lstat()
        _require(not stat.S_ISLNK(info.st_mode) and not
                 (getattr(info, 'st_file_attributes', 0) & 0x400))
    return path


def _safe_part(value):
    normalized = value.rstrip(' .').casefold()
    _require(value == value.rstrip(' .') and normalized not in _META and
             normalized.split('.', 1)[0] not in {'con', 'prn', 'aux', 'nul',
                *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))})


def _relative(value):
    _text(value, 1024)
    _require('\\' not in value and ':' not in value and '\x00' not in value)
    path = PurePosixPath(value)
    _require(not path.is_absolute() and value == path.as_posix() and
             all(part not in {'.', '..', ''} and part.lower() not in _META for part in path.parts))
    _require(bool(path.parts))
    for part in path.parts:
        _safe_part(part)
    return path


def _read(root, relative):
    path = _physical(Path(root).joinpath(*_relative(relative).parts))
    info = path.stat()
    _require(stat.S_ISREG(info.st_mode) and info.st_size <= _MAX_FILE and info.st_nlink == 1)
    with path.open('rb') as handle:
        raw = handle.read(_MAX_FILE + 1)
    _require(len(raw) <= _MAX_FILE)
    return raw


def _load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result)
            result[key] = value
        return result
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                      parse_constant=lambda _: _require(False))


def _component(value):
    _fields(value, {'ecosystem', 'name', 'version', 'kind'})
    for item in value.values():
        _text(item, 512)
    _require(value['ecosystem'] in _ECOSYSTEMS and value['kind'] in _KINDS)
    return dict(value)


def _resolved(component):
    patterns = {'npm': r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?',
                'pypi': r'\d+(?:\.\d+)*(?:[A-Za-z0-9+._-]*)',
                'nuget': r'\d+(?:\.\d+)+(?:[-+][A-Za-z0-9.-]+)?',
                'go': r'v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?'}
    version = component['version']
    return version != 'unknown' and (component['ecosystem'] not in patterns or
             re.fullmatch(patterns[component['ecosystem']], version) is not None)


@dataclass(frozen=True, init=False)
class TermsAssessment:
    repository_id: str
    binding_digest: str
    _payload: str = field(repr=False)

    def __init__(self, repository_id, binding_digest, payload, *, _seal=None):
        _require(_seal is _SEAL)
        object.__setattr__(self, 'repository_id', repository_id)
        object.__setattr__(self, 'binding_digest', binding_digest)
        object.__setattr__(self, '_payload', payload)

    def to_dict(self):
        return json.loads(self._payload)


class _Inventory:
    def __init__(self, root):
        self.root = root
        self.items = {}
        self.observed = {}
        self.errors = []
        self.total = 0
        self.direct_locks = {}

    def add(self, ecosystem, name, version, kind, path, relationship='direct'):
        component = _component(dict(ecosystem=ecosystem, name=name, version=version or 'unknown', kind=kind))
        key = tuple(component.values())
        _require(len(self.items) < _MAX_COMPONENTS or key in self.items)
        if key not in self.items:
            self.items[key] = {**component, 'component_id': 'TP-' + _digest(component)[:24],
                               'paths': [], 'relationship': relationship}
        item = self.items[key]
        if path not in item['paths']:
            item['paths'].append(path)
        if relationship == 'direct':
            item['relationship'] = 'direct'

    def read(self, path):
        raw = _read(self.root, path)
        self.total += len(raw)
        _require(self.total <= _MAX_TOTAL)
        self.observed[path] = _digest(raw)
        return raw

    def requirement(self, value, kind, path):
        _text(value)
        match = re.match(r'^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*(.*)$', value)
        _require(match is not None)
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        version = match[2].strip() or 'unknown'
        pinned = re.fullmatch(r'==([^*;,\s]+)', version)
        self.add('pypi', name, pinned[1] if pinned else version, kind, path)

    def parse(self, path, raw):
        name = PurePosixPath(path).name
        text = raw.decode('utf-8-sig')
        if name == 'pyproject.toml':
            data = tomllib.loads(text)
            if 'dependencies' in data.get('project', {}).get('dynamic', []):
                self.errors.append('TERMS_MANIFEST_DYNAMIC_DEPENDENCIES')
            if data.get('tool', {}).get('poetry'):
                self.errors.append('TERMS_MANIFEST_UNSUPPORTED_POETRY')
            for dep in data.get('project', {}).get('dependencies', []):
                self.requirement(dep, 'library', path)
            for deps in data.get('project', {}).get('optional-dependencies', {}).values():
                for dep in deps:
                    self.requirement(dep, 'development', path)
            for dep in data.get('build-system', {}).get('requires', []):
                self.requirement(dep, 'build', path)
            for deps in data.get('dependency-groups', {}).values():
                for dep in deps:
                    if type(dep) is str:
                        self.requirement(dep, 'development', path)
                    else:
                        self.errors.append('TERMS_MANIFEST_UNSUPPORTED_GROUP')
        elif name.startswith('requirements') and name.endswith('.txt'):
            for line in text.splitlines():
                line = line.split(' #', 1)[0].strip()
                if not line or line.startswith('#') or line.startswith('--hash='):
                    continue
                if line.startswith(('-', '.')) or '://' in line:
                    self.errors.append('TERMS_MANIFEST_UNRESOLVED_REQUIREMENT')
                    continue
                line = line.split(' --hash=', 1)[0].rstrip('\\').strip()
                self.requirement(line, 'development' if 'dev' in name else 'library', path)
        elif name == 'package.json':
            data = _load(raw)
            for key, kind in [('dependencies', 'library'), ('devDependencies', 'development'),
                              ('optionalDependencies', 'library'), ('peerDependencies', 'library')]:
                for dep, version in data.get(key, {}).items():
                    self.add('npm', dep, version, kind, path)
        elif name in {'package-lock.json', 'npm-shrinkwrap.json'}:
            data = _load(raw)
            packages = data.get('packages', {})
            direct = packages.get('', {})
            for location, info in packages.items():
                if not location:
                    continue
                dep = info.get('name') or location.rsplit('node_modules/', 1)[-1]
                relation = 'direct' if location == 'node_modules/' + dep and any(dep in direct.get(k, {}) for k in
                           ('dependencies', 'devDependencies', 'optionalDependencies')) else 'transitive'
                self.add('npm', dep, info.get('version', 'unknown'),
                         'development' if info.get('dev') else 'library', path, relation)
                if relation == 'direct':
                    identity = (dep, info.get('version', 'unknown'),
                                'development' if info.get('dev') else 'library')
                    self.direct_locks.setdefault(identity, set()).add(str(PurePosixPath(path).parent))
            def legacy(deps, depth=0):
                _require(depth <= 20)
                for dep, info in deps.items():
                    self.add('npm', dep, info.get('version', 'unknown'),
                             'development' if info.get('dev') else 'library', path,
                             'direct' if depth == 0 else 'transitive')
                    legacy(info.get('dependencies', {}), depth + 1)
            if not packages:
                legacy(data.get('dependencies', {}))
        elif name == 'go.mod':
            block = False
            for line in text.splitlines():
                stripped = line.split('//', 1)[0].strip()
                if stripped.startswith(('replace ', 'exclude ')):
                    self.errors.append('TERMS_MANIFEST_GO_OVERRIDE_REQUIRES_REVIEW')
                if stripped == 'require (':
                    block = True
                    continue
                if stripped == ')':
                    block = False
                match = re.match(r'^(?:require\s+)?([^\s()]+)\s+(v[^\s]+)$', stripped)
                if match and (block or stripped.startswith('require ')):
                    self.add('go', match[1], match[2], 'library', path,
                             'transitive' if '// indirect' in line else 'direct')
        elif name == 'go.sum':
            for line in text.splitlines():
                parts = line.split()
                _require(len(parts) == 3)
                self.add('go', parts[0], parts[1].removesuffix('/go.mod'), 'library', path, 'transitive')
        elif name.endswith(('.csproj', '.fsproj', '.vbproj')) or name == 'Directory.Packages.props':
            _require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper())
            tree = ET.fromstring(text)
            for node in tree.iter():
                tag = node.tag.rsplit('}', 1)[-1]
                if tag in {'PackageReference', 'PackageVersion'}:
                    dep = node.get('Include') or node.get('Update')
                    if dep:
                        version = node.get('Version') or next((c.text for c in node
                                  if c.tag.rsplit('}', 1)[-1] == 'Version'), 'unknown')
                        pinned = re.fullmatch(r'\[([^,\[\]()]+)\]', version or '')
                        if pinned:
                            version = pinned[1]
                        self.add('nuget', dep, version, 'library', path)
                elif tag == 'Reference':
                    self.errors.append('TERMS_ASSEMBLY_REQUIRES_DECLARATION')
        elif name == 'packages.lock.json':
            data = _load(raw)
            for deps in data.get('dependencies', {}).values():
                for dep, info in deps.items():
                    self.add('nuget', dep, info.get('resolved', 'unknown'), 'library', path,
                             'direct' if info.get('type') == 'Direct' else 'transitive')
        elif path == '.devsift/third-party.json':
            data = _load(raw)
            _fields(data, {'schema_version', 'components'})
            _require(data['schema_version'] == '1' and type(data['components']) is list and
                     len(data['components']) <= _MAX_COMPONENTS)
            for item in data['components']:
                _fields(item, {'ecosystem', 'name', 'version', 'kind', 'paths'})
                component = _component({k: item[k] for k in ('ecosystem', 'name', 'version', 'kind')})
                _require(type(item['paths']) is list and 0 < len(item['paths']) <= 64)
                for scope in item['paths']:
                    _relative(scope)
                self.add(**component, path=path, relationship='declared')
                for scope in item['paths']:
                    # Declared scope is itself observed; missing/unsafe bytes cannot be hidden.
                    try:
                        self.read(scope)
                    except (OSError, ValueError):
                        self.observed[scope] = 'unavailable'
                        self.errors.append('TERMS_DECLARED_USAGE_UNAVAILABLE')

    def discover(self):
        count = manifests = 0
        def walk_error(_):
            self.errors.append('TERMS_DISCOVERY_UNAVAILABLE')
        for folder, dirs, files in os.walk(self.root, followlinks=False, onerror=walk_error):
            safe = []
            for directory in sorted(dirs):
                if directory.lower() in _SKIP:
                    continue
                try:
                    _physical(Path(folder) / directory)
                    safe.append(directory)
                except (OSError, ValueError):
                    self.errors.append('TERMS_UNSAFE_PATH')
            dirs[:] = safe
            for filename in sorted(files):
                count += 1
                if count > 10000:
                    self.errors.append('TERMS_DISCOVERY_LIMIT')
                    return
                path = (Path(folder) / filename).relative_to(self.root).as_posix()
                supported = filename in {'pyproject.toml', 'package.json', 'package-lock.json',
                     'npm-shrinkwrap.json', 'go.mod', 'go.sum', 'packages.lock.json', 'Directory.Packages.props'} or \
                     filename.endswith(('.csproj', '.fsproj', '.vbproj')) or \
                     (filename.startswith('requirements') and filename.endswith('.txt')) or \
                     path == '.devsift/third-party.json'
                if not supported:
                    continue
                manifests += 1
                if manifests > 256:
                    self.errors.append('TERMS_DISCOVERY_LIMIT')
                    return
                try:
                    self.parse(path, self.read(path))
                except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, ET.ParseError):
                    self.errors.append('TERMS_MANIFEST_INVALID')
        for item in self.items.values():
            item['paths'].sort()
        self.reconcile()

    def reconcile(self):
        """Join simple npm ranges with matching direct locks in the same folder.

        Complex ranges/workspaces remain separately unresolved. Never pretend a
        lock for another workspace or a nested transitive copy resolved them.
        """
        remove = []
        for key, item in self.items.items():
            if item['ecosystem'] != 'npm':
                continue
            match = re.fullmatch(r'([~^])(\d+)\.(\d+)\.(\d+)', item['version'])
            if not match:
                continue
            manifests = {str(PurePosixPath(path).parent) for path in item['paths']
                         if PurePosixPath(path).name == 'package.json'}
            candidates = []
            for candidate in self.items.values():
                version = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', candidate['version'])
                if not version or candidate['name'] != item['name'] or candidate['kind'] != item['kind'] or \
                        candidate['ecosystem'] != 'npm' or candidate['relationship'] != 'direct':
                    continue
                direct_workspaces = self.direct_locks.get((candidate['name'], candidate['version'], candidate['kind']), set())
                if not manifests or not manifests <= direct_workspaces:
                    continue
                wanted, actual = tuple(map(int, match.groups()[1:])), tuple(map(int, version.groups()))
                upper = (wanted[0] + 1, 0, 0) if match[1] == '^' and wanted[0] else \
                        (0, wanted[1] + 1, 0) if match[1] == '^' and wanted[1] else \
                        (0, 0, wanted[2] + 1) if match[1] == '^' else (wanted[0], wanted[1] + 1, 0)
                if wanted <= actual < upper:
                    candidates.append(candidate)
            if len(candidates) == 1:
                candidates[0]['paths'] = sorted(set(candidates[0]['paths'] + item['paths']))
                remove.append(key)
        for key in remove:
            del self.items[key]


def _catalog(path, digest, now):
    _require(path is not None and digest is not None and type(digest) is str and _HEX.fullmatch(digest))
    selected = _physical(Path(path))
    _require(selected.is_absolute())
    raw = _read(selected.parent, selected.name)
    _require(_digest(raw) == digest)
    data = _load(raw)
    _fields(data, {'schema_version', 'policy_version', 'reviewer', 'reviewed_at', 'review_due', 'reviews'})
    _require(data['schema_version'] == '1')
    _text(data['policy_version'], 128)
    _text(data['reviewer'], 256)
    start, due = _timestamp(data['reviewed_at']), _timestamp(data['review_due'])
    _require(start < due and type(data['reviews']) is list and len(data['reviews']) <= _MAX_COMPONENTS)
    identities = set()
    for review in data['reviews']:
        _fields(review, {'component', 'rule_id', 'applicability', 'conclusion', 'seriousness',
                         'rationale', 'recommendation', 'evidence', 'usage_evidence'})
        component = _component(review['component'])
        _text(review['rule_id'], 128)
        _text(review['rationale'])
        _text(review['recommendation'])
        _require(review['applicability'] in {'applicable', 'not_applicable', 'unknown'} and
                 review['conclusion'] in {'compliant', 'conflict', 'unknown'} and
                 review['seriousness'] in {'serious', 'ordinary', 'unknown'})
        identity = (*(component[key] for key in ('ecosystem', 'name', 'version', 'kind')), review['rule_id'])
        _require(identity not in identities)
        identities.add(identity)
        for key in ('evidence', 'usage_evidence'):
            _require(type(review[key]) is list and len(review[key]) <= 16)
            for entry in review[key]:
                fields = {'url', 'title', 'section', 'snapshot', 'sha256', 'excerpt'} if key == 'evidence' else {'path', 'sha256', 'excerpt'}
                _fields(entry, fields)
                _require(type(entry['sha256']) is str and _HEX.fullmatch(entry['sha256']))
                _text(entry['excerpt'], 16000, multiline=True)
                _relative(entry['snapshot' if key == 'evidence' else 'path'])
                if key == 'evidence':
                    _text(entry['title'], 512)
                    _text(entry['section'], 512)
                    _text(entry['url'], 2048)
                    url = urlsplit(entry['url'])
                    _require(url.scheme == 'https' and url.hostname and not url.username and
                             not url.password and not url.query and not url.fragment)
    return data, selected.parent, start <= now < due


def _prove(review, catalog_root, repo_root, observed, cache):
    valid = True
    actual = []
    display = {'evidence': [], 'usage_evidence': []}
    for key, root, filename in [('evidence', catalog_root, 'snapshot'),
                                ('usage_evidence', repo_root, 'path')]:
        for entry in review[key]:
            shown = dict(entry)
            shown['excerpt'] = '[Unverified excerpt omitted]'
            try:
                key_path = (str(root), entry[filename])
                if key_path not in cache:
                    raw = _read(root, entry[filename])
                    _require(sum(len(value) for value in cache.values()) + len(raw) <= _MAX_TOTAL)
                    cache[key_path] = raw
                raw = cache[key_path]
                digest = _digest(raw)
                if key == 'usage_evidence':
                    observed[entry['path']] = digest
                actual.append([key, entry[filename], digest])
                text = raw.decode('utf-8')
                proven = digest == entry['sha256'] and entry['excerpt'] in text
                valid = valid and proven
                if proven:
                    start = text.index(entry['excerpt'])
                    secrets = tuple(sorted({match[1] for match in _QUOTED_SECRET.finditer(text)}))
                    shown['excerpt'] = Redactor(secrets=secrets).slice(text, start, start + len(entry['excerpt'])) \
                        if len(secrets) <= 256 else '[REDACTED]'
            except (OSError, ValueError, UnicodeError):
                valid = False
                actual.append([key, entry[filename], 'unavailable'])
            display[key].append(shown)
    needs_usage = review['applicability'] == 'applicable' and review['conclusion'] in {'compliant', 'conflict'}
    valid = valid and bool(review['evidence']) and (not needs_usage or bool(review['usage_evidence']))
    return valid, actual, display


def assess_terms(repo_root, *, catalog_path=None, catalog_digest=None, history=None, as_of=None):
    """Assess local evidence without fetching, executing or changing the project."""
    from .terms_memory import DecisionHistory, read_history, repository_identity
    errors = []
    root = Path(repo_root).absolute()
    now = datetime.now(timezone.utc) if as_of is None else as_of
    _require(isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset().total_seconds() == 0)
    try:
        _physical(root)
        _require(root.is_dir())
        repository_id = repository_identity(root)
    except (OSError, ValueError):
        errors.append('TERMS_REPOSITORY_UNAVAILABLE')
        repository_id = _digest({'unavailable_repository': str(root)})
    try:
        history = read_history(root) if history is None else history
        _require(type(history) is DecisionHistory and history.repository_id == repository_id)
        events = list(history.events)
        revision = history.revision
        if len(_json(events)) > 500_000:
            events = []
            errors.append('TERMS_HISTORY_LIMIT')
    except (OSError, ValueError):
        errors.append('TERMS_HISTORY_UNAVAILABLE')
        events, revision = [], 'unavailable'
    inventory = _Inventory(root)
    if not errors or 'TERMS_REPOSITORY_UNAVAILABLE' not in errors:
        inventory.discover()
    errors.extend(inventory.errors)
    policy = 'unreviewed'
    reviews, catalog_root, fresh = [], None, False
    catalog_binding = None
    if catalog_path is not None or catalog_digest is not None:
        try:
            data, catalog_root, fresh = _catalog(catalog_path, catalog_digest, now)
            policy, reviews = data['policy_version'], data['reviews']
            catalog_binding = catalog_digest
            if not fresh:
                errors.append('TERMS_CATALOG_STALE')
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
            errors.append('TERMS_CATALOG_INVALID')
            catalog_binding = 'invalid'
    cases = []
    proof_cache = {}
    for component in sorted(inventory.items.values(), key=lambda item: item['component_id']):
        identity = {key: component[key] for key in ('ecosystem', 'name', 'version', 'kind')}
        matches = [review for review in reviews if review['component'] == identity]
        for review in matches or [None]:
            rule = review['rule_id'] if review else 'terms-review-required'
            case_id = 'TERMS-' + _digest([identity, rule])[:24]
            actual = []
            display = {'evidence': [], 'usage_evidence': []}
            status = 'unknown'
            if review:
                proof, actual, display = _prove(review, catalog_root, root, inventory.observed, proof_cache)
                if not fresh:
                    status = 'stale'
                elif not proof or not _resolved(component):
                    status = 'potential_conflict' if review['conclusion'] == 'conflict' else 'unknown'
                elif review['applicability'] == 'not_applicable':
                    status = 'reviewed_not_applicable'
                elif review['applicability'] == 'applicable':
                    if review['conclusion'] == 'compliant':
                        status = 'reviewed_compliant'
                    elif review['conclusion'] == 'conflict':
                        status = 'confirmed_serious_conflict' if review['seriousness'] == 'serious' else 'confirmed_conflict'
            evidence_digest = _digest([review, actual, [(p, inventory.observed.get(p)) for p in component['paths']]])
            fingerprint = _digest([identity, rule, policy, evidence_digest])
            previous = [event for event in events if event.get('case_id') == case_id]
            matching = [event for event in previous if event.get('fingerprint') == fingerprint and
                        event.get('evidence_digest') == evidence_digest]
            decision = matching[-1] if matching else None
            # A later reconsideration or stale event must not resurrect an earlier waiver.
            if previous and decision is not previous[-1]:
                decision = None
            severe = status == 'confirmed_serious_conflict'
            incomplete = status in {'unknown', 'potential_conflict', 'stale'}
            if incomplete:
                decision = None
            required = (severe and (decision is None or decision.get('choice') not in {'decline', 'remediate'})) or \
                       (incomplete and bool(previous))
            cases.append(dict(case_id=case_id, fingerprint=fingerprint, evidence_digest=evidence_digest,
                component=dict(component), rule_id=rule, status=status,
                severity='Critical' if severe else 'Warning' if incomplete or status == 'confirmed_conflict' else 'Suggestion',
                enforcement='block' if severe else 'incomplete' if incomplete else 'advisory',
                title='Third-party terms: ' + status.replace('_', ' '),
                rationale=review['rationale'] if review else 'No applicable operator-reviewed evidence was supplied.',
                recommendation=review['recommendation'] if review else
                    'Study applicable official rules and actual use; supply a fresh digest-pinned reviewed catalog.',
                evidence=display['evidence'], usage_evidence=display['usage_evidence'],
                decision=decision, decision_required=bool(required), history=previous,
                limitations=['Local evidence only; no legal certification.'] +
                    (['Proof is missing, stale or does not match current bytes.'] if incomplete else [])))
    enforced = sum(case['enforcement'] == 'block' for case in cases)
    complete = not errors and all(case['enforcement'] != 'incomplete' for case in cases)
    binding = _digest(dict(policy=policy, catalog=catalog_binding, observed=inventory.observed,
                          inventory=list(inventory.items.values()), revision=revision,
                          states=[[c['fingerprint'], c['status'], c['decision_required']] for c in cases], errors=errors))
    wire = dict(schema_version='1', policy_version=policy, repository_id=repository_id,
                status='blocked' if enforced else 'incomplete' if not complete else 'clear' if cases else 'not_applicable',
                complete=complete, enforced_count=enforced, decision_required=any(c['decision_required'] for c in cases),
                input_digest=binding, history_revision=revision,
                scope=dict(formats=['Python pyproject/requirements', 'npm package/lock', 'Go mod/sum',
                                   '.NET project/lock', '.devsift/third-party.json'],
                           examined_files=sorted(inventory.observed),
                           unmatched_decisions=[event for event in events if event.get('case_id') not in
                                                {case['case_id'] for case in cases}],
                           coverage='Bounded local manifest and explicit service declarations only.'),
                inventory=sorted(inventory.items.values(), key=lambda item: item['component_id']),
                cases=cases, errors=sorted(set(errors)), limitations=[
                    'Implicit SaaS use, account plans, deployment context and embedded runtimes require explicit evidence.',
                    'Manifest discovery is not complete transitive, licensing or SaaS analysis.',
                    'Official source identity and applicability are operator-reviewed assertions, not authenticated by a digest.',
                    'No network requests, dependency installs, target execution or project writes were performed.'])
    try:
        safe = Redactor().redact(wire, max_nodes=200000)
    except RedactionError:
        # Preserve the serious floor even when public display exceeds the safe
        # budget. Explicit incompleteness prevents treating omitted data as clear.
        wire['complete'] = False
        wire['status'] = 'blocked' if enforced else 'incomplete'
        wire['errors'].append('TERMS_OUTPUT_LIMIT')
        wire['scope'].update(abbreviated_case_count=len(cases), omitted_case_count=0,
            omitted_serious_case_count=0, omitted_inventory_count=len(wire['inventory']),
            omitted_evidence_count=sum(len(case['evidence']) + len(case['usage_evidence']) for case in cases),
            omitted_history_event_count=sum(len(case['history']) for case in cases) +
                                        len(wire['scope']['unmatched_decisions']))
        wire['inventory'] = []
        wire['scope']['examined_files'] = []
        wire['scope']['unmatched_decisions'] = []
        for case in cases:
            case.update(evidence=[], usage_evidence=[], decision=None, history=[],
                        title='Third-party terms (bounded display)',
                        rationale='Full display exceeds output limits.',
                        recommendation='Reduce input scope and reassess.',
                        decision_required=case['enforcement'] == 'block',
                        limitations=['Display abbreviated; review incomplete.'])
            case['component']['paths'] = []
            for key in ('name', 'version'):
                case['component'][key] = case['component'][key][:64]
            case['rule_id'] = case['rule_id'][:64]
        wire['decision_required'] = any(case['decision_required'] for case in cases)
        binding = _digest([binding, 'TERMS_OUTPUT_LIMIT'])
        wire['input_digest'] = binding
        safe = Redactor().redact(wire, max_nodes=200000)
    return TermsAssessment(repository_id, binding, _json(safe), _seal=_SEAL)
