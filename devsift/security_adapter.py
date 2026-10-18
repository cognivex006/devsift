"""Bounded credential-shape candidates in static literals, never live validation."""
import ast
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
import hashlib
import json
import re

from .adapters import AdapterCapability, LANGUAGES
from .evidence import SourceEvidence, verify_source
from .inventory import SourceTarget, _canonical
from .native_host import source_offsets
from .redaction import Redactor
from .registry import RULES
from .scanner import AdapterOutcome, ScanFinding, _snapshot_matches_commit


_PAT = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{50,255})\Z")
_AWS = re.compile(r"[A-Za-z0-9/+=]{40}\Z")
_PEM_LABELS = ("PRIVATE KEY", "RSA PRIVATE KEY", "EC PRIVATE KEY", "OPENSSH PRIVATE KEY")
_BASE64 = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
_KEY = re.compile(r'''(?:["']([A-Za-z_][A-Za-z0-9_]*)["']|([A-Za-z_][A-Za-z0-9_]*))\s*(?::=|:|=)\s*$''')


class _Discard:
    def write(self, value):
        return len(value)

    def flush(self):
        pass


@dataclass(frozen=True)
class _Literal:
    start: int
    end: int
    value: str = field(repr=False)
    key: str = field(default="", repr=False)


def _python_literals(text):
    try:
        tree = ast.parse(text)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}

        def offset(line, byte_column):
            # CPython AST columns are UTF-8 bytes. Its physical lines are LF;
            # splitlines would also split LS/PS/VT, so use LF chunks explicitly.
            chunks = text.split("\n")
            return sum(len(chunk) + 1 for chunk in chunks[:line - 1]) + len(chunks[line - 1].encode()[:byte_column].decode())

        literals = []
        for node in ast.walk(tree):
            if type(node) is not ast.Constant or type(node.value) is not str:
                continue
            parent = parents.get(node)
            key = ""
            if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and parent.value is node:
                target = parent.targets[0] if isinstance(parent, ast.Assign) else parent.target
                if isinstance(target, ast.Name): key = target.id
                elif isinstance(target, ast.Attribute): key = target.attr
                elif isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and type(target.slice.value) is str:
                    key = target.slice.value
            elif isinstance(parent, ast.Dict) and node in parent.values:
                key_node = parent.keys[parent.values.index(node)]
                if isinstance(key_node, ast.Constant) and type(key_node.value) is str: key = key_node.value
            elif isinstance(parent, ast.keyword) and parent.value is node:
                key = parent.arg or ""
            elif not isinstance(parent, ast.Return):
                continue
            literals.append(_Literal(offset(node.lineno, node.col_offset), offset(node.end_lineno, node.end_col_offset), node.value, key))
        return literals, True
    except (SyntaxError, ValueError, UnicodeError, RecursionError):
        return [], False


def _decoded(value):
    result, index = [], 0
    escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", "'": "'", '"': '"', "`": "`"}
    while index < len(value):
        char = value[index]
        if char != "\\":
            result.append(char); index += 1; continue
        index += 1
        if index >= len(value): raise ValueError()
        char = value[index]
        if char in escapes:
            result.append(escapes[char]); index += 1
        elif char in ("u", "U", "x"):
            width = {"u": 4, "U": 8, "x": 2}[char]
            digits = value[index + 1:index + 1 + width]
            if len(digits) != width or re.fullmatch(r"[0-9a-fA-F]+", digits) is None: raise ValueError()
            decoded = chr(int(digits, 16))
            if 0xD800 <= ord(decoded) <= 0xDFFF: raise ValueError()
            result.append(decoded); index += width + 1
        else:
            raise ValueError()
    return "".join(result)


def _quoted_literals(text, language):
    """Conservative lexical contexts, not full language parsing or taint flow."""
    literals, index, complete = [], 0, True
    while index < len(text):
        if text.startswith("//", index) and language != "sql" or language == "sql" and text.startswith("--", index):
            end = text.find("\n", index)
            index = len(text) if end < 0 else end + 1
            continue
        if text.startswith("/*", index):
            depth, index = 1, index + 2
            while index < len(text) and depth:
                if text.startswith("/*", index): depth += 1; index += 2
                elif text.startswith("*/", index): depth -= 1; index += 2
                else: index += 1
            if depth: complete = False
            continue
        if language in {"javascript", "typescript"} and text[index] == "/":
            # Regex bodies are data, even if they contain quotes and assignment
            # text. Prove only a narrow expression-start context; division and
            # syntactically ambiguous slashes remain incomplete.
            before = text[max(0, index - 1024):index].rstrip()
            proven = not before or before[-1] in "=(:,[!&|?{};" or re.search(r"\b(?:return|throw|case|yield)\s*$", before) is not None
            if not proven: complete = False
            index += 1
            in_class, closed = False, False
            while index < len(text):
                char = text[index]
                if char in "\r\n": break
                if char == "\\": index += 2; continue
                if char == "[": in_class = True
                elif char == "]": in_class = False
                elif char == "/" and not in_class:
                    index += 1; closed = True; break
                index += 1
            if not closed: complete = False
            while index < len(text) and text[index].isascii() and text[index].isalpha(): index += 1
            continue
        if (language in {"csharp", "go"} and text[index] == "'"
                or language == "sql" and text[index] in '["'):
            opener = text[index]
            closer = "]" if opener == "[" else opener
            index += 1
            closed = False
            while index < len(text):
                if text[index] == closer:
                    if language == "sql" and text[index:index + 2] == closer * 2:
                        index += 2; continue
                    index += 1; closed = True; break
                if text[index] == "\\" and language != "sql": index += 2
                else: index += 1
            if not closed: complete = False
            continue
        quote = text[index]
        allowed = "'" if language == "sql" else '"`' if language == "go" else '"' if language == "csharp" else "'\"`"
        if quote not in allowed:
            index += 1; continue
        start = index
        prefix = text[max(0, start - 1024):start].rstrip()
        verbatim = language == "csharp" and prefix.endswith("@")
        interpolated = language == "csharp" and "$" in prefix[-2:]
        if language == "sql" and prefix[-1:].lower() == "n": prefix = prefix[:-1].rstrip()
        if language == "csharp": prefix = prefix.rstrip("@$").rstrip()
        raw_width = 1
        if language == "csharp" and text.startswith('"""', index):
            while index + raw_width < len(text) and text[index + raw_width] == quote: raw_width += 1
        delimiter = quote * raw_width
        index += raw_width
        body_start = index
        chunks = []
        closed = False
        while index < len(text):
            if text.startswith(delimiter, index):
                if raw_width == 1 and (verbatim or language == "sql") and text.startswith(quote * 2, index):
                    chunks.append(text[body_start:index] + quote); index += 2; body_start = index; continue
                chunks.append(text[body_start:index]); index += raw_width; closed = True; break
            if text[index] == "\\" and raw_width == 1 and quote != "`" and language != "sql" and not verbatim:
                index += 2
            else: index += 1
        if not closed:
            complete = False; break
        try:
            raw = "".join(chunks)
            if interpolated or quote == "`" and language in ("javascript", "typescript") and "${" in raw:
                complete = False; continue
            value = raw if raw_width > 1 or quote == "`" or verbatim or language == "sql" else _decoded(raw)
            assignment = prefix.endswith(("=", ":")) and not prefix.endswith(("==", "!=", "<=", ">=", "=>"))
            if not assignment:
                continue
            matched = _KEY.search(prefix)
            key = "" if matched is None else matched.group(1) or matched.group(2)
            typed = {
                "typescript": r"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*(?::\s*(?:string|unknown|any))?\s*=\s*$",
                "javascript": r"(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*$",
                "go": r"(?:var|const)\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+string)?\s*=\s*$",
                "sql": r"DECLARE\s+@([A-Za-z_][A-Za-z0-9_]*)\s+(?:nvarchar|varchar|nchar|char)(?:\(\s*(?:max|\d+)\s*\))?\s*=\s*$",
            }.get(language)
            if typed:
                declaration = re.search(typed, prefix, re.IGNORECASE)
                if declaration: key = declaration.group(1)
            literals.append(_Literal(start, index, value, key))
        except (ValueError, UnicodeError):
            complete = False
    return literals, complete


def _candidate(literal):
    value = literal.value
    if _PAT.fullmatch(value): return True
    key = literal.key.replace("_", "").lower()
    if key in {"awssecretaccesskey", "secretaccesskey"} and _AWS.fullmatch(value):
        return "EXAMPLE" not in value.upper() and "YOUR" not in value.upper()
    # Header/footer extraction and one body pass avoid overlapping whitespace
    # quantifiers/backtracking on malformed or whitespace-only key text.
    value = value.strip()
    for label in _PEM_LABELS:
        header, footer = "-----BEGIN " + label + "-----", "-----END " + label + "-----"
        if not value.startswith(header): continue
        if not value.endswith(footer): return False
        body = value[len(header):-len(footer)]
        if not 32 <= len(body) <= 65536: return False
        characters = 0
        for char in body:
            if char in _BASE64: characters += 1
            elif not char.isspace(): return False
        return characters >= 32
    return False


def _region(text, start, end):
    from .evidence import Region
    def position(offset):
        prefix = text[:offset]
        return prefix.count("\n") + 1, offset - prefix.rfind("\n")
    return Region(*position(start), *position(end))


class SecurityAdapter:
    """One composed capability, with canonical messages and conservative proof."""
    def __init__(self, delegate=None, *, repo_root=None, source_sha=None, repository="local", config_paths=(), redactor=None,
                 complete_run=False):
        try:
            if (type(complete_run) is not bool or type(config_paths) is not tuple
                    or (not complete_run and len(config_paths) > 1000)
                    or len(set(config_paths)) != len(config_paths)): raise ValueError()
            self.complete_run = complete_run
            paths = frozenset(_canonical(path) for path in config_paths)
            if redactor is not None and type(redactor) is not Redactor: raise ValueError()
            if delegate is None:
                languages, identity = tuple(sorted(LANGUAGES)), "devsift-security"
                delegate_available = True
            else:
                with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
                    capability = delegate.capability
                    if type(capability) is not AdapterCapability or not callable(delegate.analyze): raise ValueError()
                    AdapterCapability(capability.adapter_id, capability.version, capability.languages, capability.available)
                languages = capability.languages
                delegate_available = capability.available
                identity = "security-" + hashlib.sha256(capability.adapter_id.encode()).hexdigest()[:16]
            self.delegate, self.repo_root, self.source_sha = delegate, repo_root, source_sha
            self._delegate_available = delegate_available
            self.repository, self.config_paths, self.redactor = repository, paths, redactor or Redactor()
            self.capability = AdapterCapability(identity, "1.1.0", languages, True)
        except Exception:
            raise ValueError("Invalid security adapter configuration") from None

    def _proof(self, target, region, sensitive):
        if self.repo_root is None or self.source_sha is None: return SourceEvidence()
        try:
            source = verify_source(self.repo_root, self.repository, self.source_sha, target.path, region,
                                   redactor=self.redactor, sensitive=sensitive,
                                   source_timeout_seconds=None if self.complete_run else 10)
            if source.status != "VERIFIED" or not _snapshot_matches_commit(self.repo_root, source, target.content):
                return SourceEvidence(reason="SOURCE_MISMATCH")
            return source
        except Exception:
            return SourceEvidence()

    def analyze(self, target):
        if (type(target) is not SourceTarget or target.status != "ready" or target.language not in self.capability.languages
                or type(target.content) is not bytes
                or (not self.complete_run and len(target.content) > 2_000_000)):
            return AdapterOutcome(False)
        try:
            text = target.content.decode("utf-8")
            if "\x00" in text: return AdapterOutcome(False)
            literals, complete = _python_literals(text) if target.language == "python" else _quoted_literals(text, target.language)
            candidates = [literal for literal in literals if _candidate(literal)]
            if not self.complete_run and len(candidates) > 1000: return AdapterOutcome(False)
            findings, identities = [], set()
            reason = ''
            spans = [(literal.start, literal.end) for literal in candidates]

            def add(rule_id, region, source, unresolved_id=None):
                identity = (rule_id, region, unresolved_id if region is None else None)
                if identity in identities: return
                identities.add(identity)
                bounds = source_offsets(text, region) if region is not None else None
                raw = text[bounds[0]:bounds[1]] if bounds is not None else unresolved_id
                case = "SECRET-" + hashlib.sha256(json.dumps([rule_id, target.path, None if region is None else region.to_dict(), raw], sort_keys=True).encode()).hexdigest()[:24]
                findings.append(ScanFinding(case, rule_id, source, RULES[rule_id].title))

            for literal in candidates:
                region = _region(text, literal.start, literal.end)
                rule_id = "CFG003" if target.path in self.config_paths else "HC002"
                add(rule_id, region, self._proof(target, region, True))
            if target.language == "python":
                from .security_context import python_contexts
                contexts = python_contexts(text, complete_run=self.complete_run)
                complete = complete and contexts.complete
                for diagnostic in contexts.diagnostics:
                    start, end = source_offsets(text, diagnostic.region)
                    sensitive = diagnostic.rule_id == "SEC001" or any(left < end and right > start for left, right in spans)
                    add(diagnostic.rule_id, diagnostic.region,
                        self._proof(target, diagnostic.region, sensitive))
            if self.delegate is not None:
                try:
                    with redirect_stdout(_Discard()), redirect_stderr(_Discard()):
                        delegated = self.delegate.analyze(target)
                    if type(delegated) is not AdapterOutcome: raise ValueError()
                    AdapterOutcome(delegated.complete, delegated.findings, reason=delegated.reason)
                    complete = complete and delegated.complete and self._delegate_available
                    if not delegated.complete:
                        reason = delegated.reason
                    seen_cases = {}
                    for finding in delegated.findings:
                        ScanFinding(finding.case_id, finding.rule_id, finding.source, finding.message, finding.lifecycle_class)
                        rule_id = "CFG003" if finding.rule_id == "HC002" and target.path in self.config_paths else finding.rule_id
                        if finding.source.status != "VERIFIED":
                            complete = False
                            add(rule_id, None, SourceEvidence(), finding.case_id)
                            continue
                        location = finding.source.location
                        if location.path != target.path:
                            complete = False
                            add(rule_id, None, SourceEvidence(), finding.case_id)
                            continue
                        region = location.region
                        start, end = source_offsets(text, region)
                        identity = (finding.rule_id, region)
                        if finding.case_id in seen_cases and seen_cases[finding.case_id] != identity: complete = False
                        seen_cases[finding.case_id] = identity
                        sensitive = finding.rule_id in {"HC002", "CFG003", "SEC001"} or any(left < end and right > start for left, right in spans)
                        add(rule_id, region, self._proof(target, region, sensitive))
                except Exception:
                    complete = False
            findings.sort(key=lambda finding: (finding.rule_id, finding.case_id))
            return AdapterOutcome(complete, tuple(findings), reason=(
                reason or ('COMPLETED' if complete else 'SECURITY_ANALYSIS_INCOMPLETE')
            ) if self.complete_run else '')
        except Exception:
            return AdapterOutcome(False)
