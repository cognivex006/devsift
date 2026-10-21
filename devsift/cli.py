"""Strict, read-only CLI with explicitly configured native analyzers."""
import argparse
import json
import sys

from .output import misuse, result


class ArgumentError(Exception):
    """A usage error whose public representation is one JSON record."""


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **(kwargs | {'allow_abbrev': False}))

    def error(self, message):
        # Do not echo user values: arguments can accidentally contain secrets.
        raise ArgumentError('Invalid arguments; run devsift <command> --help.')


def parser() -> Parser:
    from .terms_commands import add_catalog_options, add_terms_command
    root = Parser(prog='devsift', description='Read-only scans with optional explicitly trusted native analyzers.')
    commands = root.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('scan', help='Inventory targets and run explicitly configured native analyzers.')
    scope = scan.add_mutually_exclusive_group()
    scope.add_argument('--changed', action='store_true', help='Inventory staged, unstaged and untracked working-tree paths (default).')
    scope.add_argument('--all', action='store_true', help='Include legacy source as recommendations.')
    scan.add_argument('--legacy-mode', choices=['recommend'], default='recommend',
                      help='Untouched legacy is advisory; no bulk remediation.')
    scan.add_argument('--native-manifest', help='Absolute explicitly trusted native tool manifest; authorizes code execution.')
    scan.add_argument('--native-manifest-digest', help='Independently trusted SHA256 of the exact manifest bytes.')
    scan.add_argument('--security', action='store_true', help='Enable bounded credential/security-context analysis; no source edits.')
    scan.add_argument('--report-format', action='append', choices=['json', 'markdown', 'sarif'],
                      help='Include selected full report formats in the JSON envelope; default includes all three.')
    ci = commands.add_parser('ci', help='Run a fresh read-only configured scan and fail closed on incomplete work.')
    ci_scope = ci.add_mutually_exclusive_group()
    ci_scope.add_argument('--changed', action='store_true', help='Read staged, unstaged and untracked paths (default).')
    ci_scope.add_argument('--all', action='store_true', help='Analyze all eligible source snapshots.')
    ci_scope.add_argument('--paths', nargs='+', help='Explicit repository-relative paths; scope is reported as paths.')
    ci.add_argument('--native-manifest', help='Override the registered analyzer manifest with explicit trust.')
    ci.add_argument('--native-manifest-digest', help='Independently trusted lowercase SHA256 for the override.')
    ci.add_argument('--base', help='Git base ref for actual source-origin attribution; unresolved history stays incomplete.')
    ci.add_argument('--minimum-severity', choices=['Critical', 'Error'], default='Error')
    ci.add_argument('--security', action='store_true', help='Enable the bounded built-in credential detector alongside native tools.')
    ci.add_argument('--report-format', action='append', choices=['json', 'markdown', 'sarif'],
                    help='Include selected full report formats in the JSON envelope; default includes all three.')
    for execution in (scan, ci):
        storage = execution.add_mutually_exclusive_group()
        storage.add_argument('--report-dir', help='New absolute report/session directory outside source; enables resumable processing.')
        storage.add_argument('--resume', help='Resume an owned session directory after revalidating source and configuration.')
        execution.add_argument('--summary', action='store_true',
                               help='Return compact counts and complete report index; full results remain in the session.')
        execution.add_argument('--report-language', choices=('en', 'th'), default='en',
                               help='Language of the complete human-readable REPORT.md (default: en).')
    explain = commands.add_parser('explain', help='Explain a verified case (backend pending).')
    explain.add_argument('case_id', help='Exact case ID in a verified report.')
    report = commands.add_parser('report', help='Read a report (backend pending); writes no files.')
    report.add_argument('--latest', action='store_true', help='Request the latest verified report.')
    doctor = commands.add_parser('doctor', help='Diagnose providers without changes; native probes require explicit trust.')
    doctor.add_argument('--native-manifest', help='Absolute explicitly trusted native tool manifest; authorizes bounded probes.')
    doctor.add_argument('--native-manifest-digest', help='Independently trusted SHA256 of the exact manifest bytes.')
    doctor.add_argument('--policy', help='Explicit JSON policy to validate read-only; no automatic discovery.')
    doctor.add_argument('--cache-path', help='Explicit cache directory to inspect without creating or changing it.')
    for execution in (scan, ci, doctor):
        add_catalog_options(execution)
    setup = commands.add_parser('setup', help='Register trusted analyzers once; scans never build or install tools.')
    setup.add_argument('--status', action='store_true', help='Check the registered analyzers without changing configuration.')
    setup.add_argument('--native-manifest', help='Explicit absolute operator-approved manifest to register.')
    setup.add_argument('--native-manifest-digest', help='Independently trusted SHA256 of that manifest.')
    setup.add_argument('--analyzer-bundle', help='Explicit verified platform analyzer ZIP to deploy and register.')
    setup.add_argument('--bundle-digest', help='Independently trusted SHA256 of the analyzer ZIP.')
    setup.add_argument('--home', help='Explicit installation home (defaults to the current user home).')
    prompt = commands.add_parser('prompt', help='Request a case prompt; never executes remediation.')
    prompt.add_argument('case_id')
    prompt.add_argument('--mode', choices=['review', 'implement'], required=True)
    prompt.add_argument('--approved-case', help='Bind the implementation target case; matching the ID alone grants no authority.')
    prompt.add_argument('--scan-input', help='Explicit scan JSON to reassemble and reprove against this Git root.')
    prompt.add_argument('--approval-file', help='Explicit operator approval JSON; never discovered or treated as a signature.')
    add_terms_command(commands)
    return root


def _execution_reports(public_record, scan_record, **options):
    """Attach reports to fresh, already-redacted execution output only.

    A bounded report renderer can fail independently of a successful scan. Keep
    its safe findings and coverage available, while refusing a complete result.
    Never use this helper for imported/untrusted scan documents.
    """
    from .ci_artifacts import attach_reports
    if options.get('terms_assessment') is not None:
        from .terms_gate import source_record
        scan_record = source_record(scan_record, options['terms_assessment'])
    rendered = attach_reports(public_record, scan_record, **options)
    if any(error['code'] == 'REPORT_UNAVAILABLE' for error in rendered['errors']):
        return {**public_record, 'complete': False, 'status': 'incomplete', 'exit_code': 2,
                'errors': [*public_record['errors'], *rendered['errors']],
                'data': {**public_record['data'], 'reports': {}, 'report_status': 'unavailable'}}
    return rendered


def _stored_execution(args, factory, *, policy=None, trusted_lifecycles=False):
    """Keep full-run state outside source; do not grant trust to target config."""
    import hashlib
    import os
    import sqlite3
    from pathlib import Path
    import subprocess
    import uuid
    from .cli_scan import _git
    from .redaction import Redactor
    from .scan_progress import ScanProgress
    from .scan_store import StoreError, run_streamed
    root = Path.cwd().resolve()
    from .terms import assess_terms
    from .terms_gate import apply_terms_gate
    terms = assess_terms(root, catalog_path=getattr(args, 'terms_catalog', None),
                         catalog_digest=getattr(args, 'terms_catalog_digest', None))
    args._terms_assessment = terms
    identity = hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()
    destination = (Path(args.resume or args.report_dir) if args.resume or args.report_dir else
                   Path.home() / '.local/share/devsift/scans' / identity / uuid.uuid4().hex)
    try:
        head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}').decode('ascii').strip()
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        head = None
    configuration = {'command': args.command, 'head': head, 'all_scope': args.all,
                     'native_digest': args.native_manifest_digest, 'security': args.security,
                     'formats': args.report_format, 'policy': policy,
                     'legacy_mode': getattr(args, 'legacy_mode', None),
                     'paths': getattr(args, 'paths', None)}
    configuration['terms_binding'] = terms.binding_digest
    if args.report_language != 'en':
        configuration['report_language'] = args.report_language
    if getattr(args, 'base', None) is not None:
        try:
            configuration['base'] = _git(root, 'rev-parse', '--verify', '--end-of-options',
                                          args.base + '^{commit}').decode('ascii').strip()
        except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
            configuration['base'] = 'unresolved'
    try:
        with ScanProgress() as progress:
            def observed(hook):
                def select(target):
                    selected = hook(target)
                    progress.update(('Analyzing ' if selected else 'Reusing verified result: ')
                                    + Redactor().text(target.path))
                    if not selected:
                        progress.advance(1)
                    return selected
                iterator = iter(factory(select))
                try:
                    for record in iterator:
                        progress.advance(len(record['data'].get('targets', [])), len(record['findings']))
                        yield record
                    progress.update('Writing complete report pages and verifying coverage')
                finally:
                    if hasattr(iterator, 'close'):
                        iterator.close()
            return run_streamed(root, observed, destination=destination, resume=bool(args.resume),
                                configuration=configuration, policy=policy,
                                trusted_lifecycles=trusted_lifecycles,
                                formats=None if args.report_format is None else tuple(dict.fromkeys(args.report_format)),
                                language=args.report_language, terms_assessment=terms,
                                terms_recheck=lambda: assess_terms(root,
                                    catalog_path=getattr(args, 'terms_catalog', None),
                                    catalog_digest=getattr(args, 'terms_catalog_digest', None)))
    except KeyboardInterrupt:
        return apply_terms_gate(result(args.command, complete=False, errors=[{
            'code': 'SCAN_INTERRUPTED', 'message': 'Scan interrupted; owned session state is retained for resume.'}],
            data={'scan_directory': Redactor().text(str(destination)), 'resume_available':
                  destination.is_dir() and (destination / 'ownership.json').is_file()}), terms, include_assessment=True)
    except MemoryError:
        return apply_terms_gate(result(args.command, complete=False, errors=[{
            'code': 'SCAN_RESOURCE_EXHAUSTED',
            'message': 'Scan resource allocation failed; retained session state can be resumed.'}],
            data={'scan_directory': Redactor().text(str(destination))}), terms, include_assessment=True)
    except (StoreError, OSError, ValueError, sqlite3.Error):
        return apply_terms_gate(result(args.command, complete=False, errors=[{
            'code': 'SCAN_STORAGE_UNAVAILABLE',
            'message': 'Owned scan/report storage or resume configuration is unavailable.'}],
            data={'scan_directory': Redactor().text(str(destination))}), terms, include_assessment=True)


def run(args: argparse.Namespace) -> dict:
    if args.command in ('scan', 'ci', 'doctor', 'terms'):
        from .terms_commands import validate_catalog_options
        if not validate_catalog_options(args):
            raise ArgumentError('Terms catalog requires an absolute path and matching independently trusted SHA256.')
    if args.command == 'terms':
        if args.terms_action == 'check':
            return _stored_execution(args, lambda hook: iter((result('scan', complete=True,
                data={'targets': [], 'counts': {}, 'scope': 'terms_only',
                      'analysis_performed': False, 'terms_assessment_performed': True}),)))
        from .terms_commands import run_owner_command
        return run_owner_command(args)
    if args.command == 'setup':
        from .analyzer_setup import SetupError, deploy, register, registered, ready
        from .native_manifest import load_manifest
        from .native_host import probe_tool
        from pathlib import Path
        import zipfile
        import zlib
        home = None if args.home is None else Path(args.home)
        native = args.native_manifest is not None or args.native_manifest_digest is not None
        bundle = args.analyzer_bundle is not None or args.bundle_digest is not None
        if ((int(args.status) + int(native) + int(bundle)) != 1 or
                native and (args.native_manifest is None or args.native_manifest_digest is None) or
                bundle and (args.analyzer_bundle is None or args.bundle_digest is None)):
            raise ArgumentError('Use setup --status, a trusted manifest pair, or a trusted analyzer bundle pair.')
        try:
            if args.status:
                saved = registered(home)
                if saved is None:
                    raise SetupError('No analyzers registered; reinstall DevSift or register an approved manifest with setup.')
                entries = load_manifest(*saved)
                available = all(ready(entry.tool) for entry in entries)
                return result('setup', complete=available, data={'analysis_performed': False, 'analysis_ready': available,
                    'registered_tools': [entry.tool.tool_id for entry in entries],
                    'languages': sorted({language for entry in entries for language in entry.tool.languages})},
                    errors=[] if available else [{'code': 'NATIVE_TOOL_UNAVAILABLE', 'message': 'Registered tools failed readiness checks; run devsift doctor.'}])
            state = (deploy(args.analyzer_bundle, args.bundle_digest, home=home) if bundle else
                     register(args.native_manifest, args.native_manifest_digest, home=home))
            return result('setup', complete=True, data=state)
        except SetupError as error:
            return result('setup', complete=False, errors=[{'code': 'ANALYZER_SETUP_UNAVAILABLE',
                'message': str(error)}],
                data={'analysis_performed': False, 'analysis_ready': False, 'probes': error.probes})
        except (OSError, ValueError, TypeError, KeyError, RecursionError,
                zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError):
            return result('setup', complete=False, errors=[{'code': 'ANALYZER_SETUP_UNAVAILABLE',
                'message': 'Analyzer setup failed validation or readiness. Previous registration was preserved; run devsift setup --help.'}],
                data={'analysis_performed': False, 'analysis_ready': False})
    if args.command in ('scan', 'doctor', 'ci'):
        from .analyzer_setup import SetupError, resolve
        from pathlib import Path
        import re
        if (args.native_manifest is None) != (args.native_manifest_digest is None):
            raise ArgumentError('Native manifest and digest must be supplied together.')
        if args.native_manifest is not None and (not Path(args.native_manifest).is_absolute()
                or re.fullmatch('[0-9a-f]{64}', args.native_manifest_digest) is None):
            raise ArgumentError('Native manifest requires an absolute path and lowercase SHA256 digest.')
        try:
            configured = resolve(args.native_manifest, args.native_manifest_digest)
        except SetupError:
            failure = result(args.command, complete=False, errors=[{'code': 'REGISTERED_ANALYZERS_UNAVAILABLE',
                'message': 'Registered analyzer configuration changed or is unavailable. Run devsift doctor or reinstall DevSift; do not approve project-supplied manifests.'}])
            if args.command in ('scan', 'ci'):
                return _stored_execution(args, lambda hook: iter((failure,)))
            from .terms_gate import attach_readiness
            return attach_readiness(failure, Path.cwd(), catalog_path=args.terms_catalog,
                                    catalog_digest=args.terms_catalog_digest)
        if configured is not None:
            args.native_manifest, args.native_manifest_digest = configured
        elif args.command == 'ci':
            failure = result('ci', complete=False, errors=[{'code': 'ANALYZER_SETUP_REQUIRED',
                'message': 'No analyzers registered. Reinstall DevSift or register an operator-approved manifest with devsift setup.'}])
            return _stored_execution(args, lambda hook: iter((failure,)))
    if args.command == 'prompt':
        if args.mode == 'implement' and args.approved_case != args.case_id:
            raise ArgumentError('Implement mode requires --approved-case matching the case ID.')
        if args.mode == 'review' and (args.approved_case is not None or args.approval_file is not None):
            raise ArgumentError('Approval options are valid only for implement mode.')
        if args.approval_file is not None and args.scan_input is None:
            raise ArgumentError('Approval input requires an explicit scan input.')
        if args.scan_input is not None:
            from pathlib import Path
            from .case_command import run_case_command
            return run_case_command(args.case_id, mode=args.mode, scan_input=args.scan_input,
                                    repo_root=Path.cwd(), approved_case=args.approved_case,
                                    approval_file=args.approval_file)
    data = {}
    if args.command == 'doctor':
        from pathlib import Path
        import re
        from .doctor import run_doctor
        if (args.native_manifest is None) != (args.native_manifest_digest is None):
            raise ArgumentError('Native manifest and digest must be supplied together.')
        if args.native_manifest is not None and (not Path(args.native_manifest).is_absolute()
                or re.fullmatch('[0-9a-f]{64}', args.native_manifest_digest) is None):
            raise ArgumentError('Native manifest requires an absolute path and lowercase SHA256 digest.')
        diagnostics = run_doctor(native_manifest=args.native_manifest,
                                 native_manifest_digest=args.native_manifest_digest,
                                 root=Path.cwd(), policy_path=args.policy, cache_path=args.cache_path)
        diagnostics['data']['capabilities'].update(reports=True, case_prompts=True)
        from .terms_gate import attach_readiness
        return attach_readiness(diagnostics, Path.cwd(), catalog_path=args.terms_catalog,
                                catalog_digest=args.terms_catalog_digest)
    elif args.command == 'ci':
        from pathlib import Path
        import re
        from .ci_gate import GateConfig, run_ci
        if (not Path(args.native_manifest).is_absolute()
                or re.fullmatch('[0-9a-f]{64}', args.native_manifest_digest) is None):
            raise ArgumentError('CI requires an absolute manifest path and lowercase SHA256 digest.')
        config = GateConfig(args.minimum_severity)
        return _stored_execution(args, lambda hook: run_ci(
            Path.cwd(), native_manifest=args.native_manifest,
            native_manifest_digest=args.native_manifest_digest, base_ref=args.base,
            all_scope=args.all, paths=None if args.paths is None else tuple(args.paths),
            security=args.security, config=config, stream=True, should_scan=hook,
            terms_assessment=args._terms_assessment, terms_catalog=args.terms_catalog,
            terms_catalog_digest=args.terms_catalog_digest),
            policy=config.policy(), trusted_lifecycles=True)
    elif args.command == 'scan':
        from pathlib import Path
        import re
        from .cli_scan import run_scan
        if (args.native_manifest is None) != (args.native_manifest_digest is None):
            raise ArgumentError('Native manifest and digest must be supplied together.')
        if args.native_manifest is not None and (not Path(args.native_manifest).is_absolute()
                or re.fullmatch('[0-9a-f]{64}', args.native_manifest_digest) is None):
            raise ArgumentError('Native manifest requires an absolute path and lowercase SHA256 digest.')
        return _stored_execution(args, lambda hook: run_scan(
            Path.cwd(), all_scope=args.all, legacy_mode=args.legacy_mode,
            native_manifest=args.native_manifest, native_manifest_digest=args.native_manifest_digest,
            security=args.security, stream=True, should_scan=hook,
            terms_assessment=args._terms_assessment, terms_catalog=args.terms_catalog,
            terms_catalog_digest=args.terms_catalog_digest))
    return result(args.command, complete=False, data=data,
                  errors=[{'code': 'CAPABILITY_UNAVAILABLE',
                           'message': 'The requested capability is unavailable in this invocation; '
                                      'no analysis or source verification was performed.'}])


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        record = run(args)
    except ArgumentError as error:
        record = misuse(str(error))
        print(json.dumps(record, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return record['exit_code']
    if type(record) is not dict:
        try:
            if args.summary:
                summary = record.summary()
                print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
                return summary['exit_code']
            else:
                return record.write_json(sys.stdout)
        finally:
            record.close()
    print(json.dumps(record, ensure_ascii=True, sort_keys=True))
    return record['exit_code']
