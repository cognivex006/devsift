"""Bounded Python AST security contexts; no imports, execution or live probing."""
import ast
from dataclasses import dataclass

from .evidence import Region


@dataclass(frozen=True)
class ContextDiagnostic:
    rule_id: str
    region: Region


@dataclass(frozen=True)
class ContextReport:
    complete: bool
    diagnostics: tuple[ContextDiagnostic, ...] = ()


_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "critical", "fatal", "exception", "log"})
_HTTP = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "request"})
_UNKNOWN = ("unknown", False)


def python_contexts(text):
    """Return only rule/region facts from explicit static binding contracts.

    Import names are not runtime module authentication. Unsupported control flow
    or lexical scope keeps analysis incomplete rather than assuming convenient
    bindings. Credential signatures are shared with the bounded T031 detector.
    """
    try:
        if type(text) is not str or len(text.encode()) > 2_000_000 or "\0" in text:
            return ContextReport(False)
        from .security_adapter import _Literal, _candidate
        tree = ast.parse(text)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        module_bindings, mutated_roots, alias_edges, security_imports = {}, set(), [], set()
        for node in ast.walk(tree):
            parent = parents.get(node)
            nested = False
            while parent is not None:
                if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                    nested = True; break
                parent = parents.get(parent)
            if nested: continue
            if isinstance(node, ast.Import):
                security_imports.update(alias.asname or alias.name for alias in node.names if alias.name in {"logging", "requests", "ssl"})
            names = []
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store): names = [node.id]
            elif isinstance(node, (ast.Import, ast.ImportFrom)): names = [alias.asname or alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): names = [node.name]
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) and isinstance(node.value, ast.Name): mutated_roots.add(node.value.id)
            for name in names: module_bindings[name] = module_bindings.get(name, 0) + 1
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Name):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                alias_edges.extend((target.id, node.value.id) for target in targets if isinstance(target, ast.Name))
        graph = {}
        for left, right in alias_edges:
            graph.setdefault(left, set()).add(right)
            graph.setdefault(right, set()).add(left)
        queue = list(mutated_roots)
        for name in queue:
            for alias in graph.get(name, ()):
                if alias not in mutated_roots: mutated_roots.add(alias); queue.append(alias)
        chunks = text.split("\n")
        starts, running = [], 0
        for chunk in chunks:
            starts.append(running); running += len(chunk) + 1
        diagnostics, seen = [], set()
        complete = not bool(mutated_roots & security_imports)

        def span(node):
            def offset(line, column):
                return len(chunks[line - 1].encode()[:column].decode()) + 1
            return Region(node.lineno, offset(node.lineno, node.col_offset),
                          node.end_lineno, offset(node.end_lineno, node.end_col_offset))

        def emit(rule, node):
            nonlocal complete
            diagnostic = ContextDiagnostic(rule, span(node))
            if diagnostic in seen: return
            if len(diagnostics) >= 1000: complete = False; return
            seen.add(diagnostic); diagnostics.append(diagnostic)

        def value(node, env, key=""):
            if isinstance(node, ast.Constant) and type(node.value) is str:
                return ("literal", bool(_candidate(_Literal(0, 0, node.value, key))))
            if isinstance(node, ast.Name): return env.get(node.id, _UNKNOWN)
            if isinstance(node, ast.Call):
                called = callee(node.func, env)
                if called == "logging.getLogger": return ("logger", False)
                if called in {"requests.Session", "requests.session"}: return ("session", False)
            return _UNKNOWN

        def callee(node, env):
            if isinstance(node, ast.Name):
                if node.id == "print" and node.id not in env: return "print"
                return env.get(node.id, _UNKNOWN)[0]
            if isinstance(node, ast.Attribute):
                owner = value(node.value, env)[0]
                if owner in {"logging", "requests", "ssl"}: return owner + "." + node.attr
                if owner == "logger" and node.attr in _METHODS: return "logging." + node.attr
                if owner == "session" and node.attr in _HTTP: return "requests." + node.attr
            return "unknown"

        def calls(node, env):
            nonlocal complete
            if node is None: return
            if isinstance(node, (ast.Lambda, ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.DictComp)):
                if relevant(node, env): complete = False
                return
            if isinstance(node, ast.Call):
                called = callee(node.func, env)
                if called == "print" or called.startswith("logging.") and called.split(".")[-1] in _METHODS:
                    arguments = list(node.args[1:] if called == "logging.log" else node.args)
                    arguments += [keyword.value for keyword in node.keywords
                                  if keyword.arg in ({"sep", "end"} if called == "print" else {"msg"})]
                    if any(value(argument, env)[1] for argument in arguments): emit("SEC001", node)
                if called == "ssl._create_unverified_context":
                    keywords = {keyword.arg: keyword.value for keyword in node.keywords}
                    if node.args or len(keywords) != len(node.keywords) or not keywords.keys() <= {"cert_reqs", "check_hostname"}:
                        complete = False
                    else:
                        requirement = callee(keywords["cert_reqs"], env) if "cert_reqs" in keywords else "ssl.CERT_NONE"
                        hostname_node = keywords.get("check_hostname")
                        hostname = False if hostname_node is None else hostname_node.value if isinstance(hostname_node, ast.Constant) and type(hostname_node.value) is bool else None
                        if requirement == "ssl.CERT_REQUIRED" and hostname is True:
                            pass  # Trusted stdlib restores both certificate and hostname checks.
                        elif requirement in {"ssl.CERT_NONE", "ssl.CERT_REQUIRED"} and hostname is False:
                            emit("SEC002", node)
                        else:
                            complete = False
                if called.startswith("requests.") and called.split(".")[-1] in _HTTP:
                    if any(keyword.arg == "verify" and isinstance(keyword.value, ast.Constant)
                           and keyword.value.value is False for keyword in node.keywords): emit("SEC002", node)
            for child in ast.iter_child_nodes(node): calls(child, env)

        def assigned(node):
            names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del))}
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and isinstance(child.ctx, (ast.Store, ast.Del)) and isinstance(child.value, ast.Name): names.add(child.value.id)
                if isinstance(child, (ast.Import, ast.ImportFrom)):
                    names.update(alias.asname or alias.name.split(".")[0] for alias in child.names)
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): names.add(child.name)
            return names

        def relevant(node, env):
            """Unsupported syntax is partial only for potential rule evidence.

            Unrelated application loops/branches/classes do not imply complete
            language analysis, but do not invalidate this bounded rule check.
            """
            if node is None: return False
            for child in ast.walk(node):
                if isinstance(child, ast.Constant) and type(child.value) is str:
                    parent, key = parents.get(child), ""
                    if isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is child:
                        target = parent.targets[0] if isinstance(parent, ast.Assign) else parent.target
                        if isinstance(target, ast.Name): key = target.id
                    elif isinstance(parent, ast.keyword): key = parent.arg or ""
                    if _candidate(_Literal(0, 0, child.value, key)): return True
                if isinstance(child, ast.Name) and value(child, env)[1]: return True
                if isinstance(child, ast.Call):
                    called = callee(child.func, env)
                    if called in {"logging.getLogger", "requests.Session", "requests.session", "ssl._create_unverified_context"}: return True
                    if called.startswith("requests.") and called.split(".")[-1] in _HTTP and any(
                        keyword.arg == "verify" and isinstance(keyword.value, ast.Constant) and keyword.value.value is False for keyword in child.keywords): return True
                if isinstance(child, ast.Import) and any(alias.name in {"logging", "requests", "ssl"} for alias in child.names): return True
                if isinstance(child, ast.ImportFrom) and child.module in {"logging", "requests", "ssl"}: return True
            return any(name in env and env[name][0] not in {"literal", "unknown"} for name in assigned(node))

        def block(statements, env):
            nonlocal complete
            for node in statements:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        env[alias.asname or alias.name.split(".")[0]] = (alias.name if alias.name in {"logging", "requests", "ssl"} else "unknown", False)
                elif isinstance(node, ast.ImportFrom):
                    if any(alias.name == "*" for alias in node.names):
                        if relevant(tree, env): complete = False
                        for name in env: env[name] = _UNKNOWN
                        env["print"] = _UNKNOWN
                        continue
                    for alias in node.names:
                        known = node.level == 0 and ((node.module == "logging" and alias.name in _METHODS | {"getLogger"})
                            or (node.module == "requests" and alias.name in _HTTP | {"Session", "session"})
                            or (node.module == "ssl" and alias.name in {"_create_unverified_context", "CERT_REQUIRED", "CERT_NONE"}))
                        env[alias.asname or alias.name] = (node.module + "." + alias.name if known else "unknown", False)
                elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                    calls(node.value, env)
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if isinstance(target, ast.Name): env[target.id] = value(node.value, env, target.id)
                        elif isinstance(target, ast.Attribute):
                            owner = value(target.value, env)[0]
                            if owner in {"logging", "requests", "ssl", "logger"}:
                                complete = False
                                for name, symbol in list(env.items()):
                                    if symbol[0] == owner: env[name] = _UNKNOWN
                            elif owner == "session":
                                if target.attr == "verify" and isinstance(node.value, ast.Constant) and node.value.value is False:
                                    emit("SEC002", node)
                                elif target.attr in _HTTP and isinstance(target.value, ast.Name): env[target.value.id] = _UNKNOWN
                            elif isinstance(target.value, ast.Name): env[target.value.id] = _UNKNOWN
                        else:
                            for name in assigned(target): env[name] = _UNKNOWN
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    env[node.name] = _UNKNOWN
                    blocked = {name for name, symbol in env.items() if symbol[0] not in {"literal", "unknown"}
                               and (module_bindings.get(name, 0) > 1 or name in mutated_roots)}
                    inner = {name: symbol for name, symbol in env.items() if symbol[0] not in {"literal", "unknown"}
                             and module_bindings.get(name, 0) <= 1 and name not in mutated_roots}
                    for name in module_bindings:
                        if name not in inner: inner[name] = _UNKNOWN
                    locals_ = set().union(*(assigned(statement) for statement in node.body)) if node.body else set()
                    locals_.update(argument.arg for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs])
                    if node.args.vararg: locals_.add(node.args.vararg.arg)
                    if node.args.kwarg: locals_.add(node.args.kwarg.arg)
                    if "print" in module_bindings and "print" not in env: blocked.add("print")
                    if blocked - locals_ and relevant(node, env): complete = False
                    for name in locals_: inner[name] = _UNKNOWN
                    block(node.body, inner)
                elif isinstance(node, ast.ClassDef):
                    env[node.name] = _UNKNOWN
                    # Class namespaces are not enclosing lexical namespaces for
                    # methods. Do not invent class-to-method binding flow.
                    if relevant(node, env): complete = False
                elif isinstance(node, (ast.Expr, ast.Return, ast.Raise, ast.Assert)):
                    calls(node, env)
                elif isinstance(node, (ast.Pass, ast.Break, ast.Continue)):
                    pass
                else:
                    # Branches, loops, query assignments and cross-scope writes
                    # are not a supported control-flow/dataflow proof domain.
                    if relevant(node, env): complete = False
                    for name in assigned(node): env[name] = _UNKNOWN
        block(tree.body, {})
        diagnostics.sort(key=lambda item: (item.region.start_line, item.region.start_column, item.rule_id))
        return ContextReport(complete, tuple(diagnostics))
    except (ValueError, TypeError, SyntaxError, UnicodeError, RecursionError):
        return ContextReport(False)
