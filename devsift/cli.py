"""Strict, read-only CLI with explicitly configured native analyzers."""
import argparse
import json
import platform
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
    ci.add_argument('--native-manifest', required=True, help='Absolute explicitly trusted executable configuration.')
    ci.add_argument('--native-manifest-digest', required=True, help='Independently trusted lowercase SHA256.')
    ci.add_argument('--base', help='Git base ref for actual source-origin attribution; unresolved history stays incomplete.')
    ci.add_argument('--minimum-severity', choices=['Critical', 'Error'], default='Error')
    ci.add_argument('--security', action='store_true', help='Enable the bounded built-in credential detector alongside native tools.')
    ci.add_argument('--report-format', action='append', choices=['json', 'markdown', 'sarif'],
                    help='Include selected full report formats in the JSON envelope; default includes all three.')
    explain = commands.add_parser('explain', help='Explain a verified case (backend pending).')
    explain.add_argument('case_id', help='Exact case ID in a verified report.')
    report = commands.add_parser('report', help='Read a report (backend pending); writes no files.')
    report.add_argument('--latest', action='store_true', help='Request the latest verified report.')
    commands.add_parser('doctor', help='Report runtime and capability availability without changes.')
    prompt = commands.add_parser('prompt', help='Request a case prompt; never executes remediation.')
    prompt.add_argument('case_id')
    prompt.add_argument('--mode', choices=['review', 'implement'], required=True)
    prompt.add_argument('--approved-case', help='Explicit approval must match this one case ID.')
    return root


def run(args: argparse.Namespace) -> dict:
    if args.command == 'prompt':
        if args.mode == 'implement' and args.approved_case != args.case_id:
            raise ArgumentError('Implement mode requires --approved-case matching the case ID.')
        if args.mode == 'review' and args.approved_case is not None:
            raise ArgumentError('--approved-case is valid only for implement mode.')
    data = {}
    if args.command == 'doctor':
        data = {'runtime': {'name': 'python', 'version': platform.python_version(),
                            'supported': sys.version_info >= (3, 12)},
                'capabilities': {'command_parser': True, 'read_only': True,
                                 'inventory': True, 'git_provenance': True,
                                 'analyzers': False, 'reports': False,
                                 'case_prompts': False}}
    elif args.command == 'ci':
        from pathlib import Path
        import re
        from .ci_artifacts import attach_reports
        from .ci_gate import GateConfig, run_ci
        if (not Path(args.native_manifest).is_absolute()
                or re.fullmatch('[0-9a-f]{64}', args.native_manifest_digest) is None):
            raise ArgumentError('CI requires an absolute manifest path and lowercase SHA256 digest.')
        config = GateConfig(args.minimum_severity)
        execution = run_ci(Path.cwd(), native_manifest=args.native_manifest,
                      native_manifest_digest=args.native_manifest_digest,
                      base_ref=args.base, all_scope=args.all,
                      paths=None if args.paths is None else tuple(args.paths), security=args.security,
                      config=config)
        return attach_reports(execution.to_dict(), execution.scan_record(), repo_root=Path.cwd(),
                              policy=config.policy(), trusted_lifecycles=True,
                              formats=None if args.report_format is None else tuple(dict.fromkeys(args.report_format)))
    elif args.command == 'scan':
        from pathlib import Path
        import re
        from .ci_artifacts import attach_reports
        from .cli_scan import run_scan
        if (args.native_manifest is None) != (args.native_manifest_digest is None):
            raise ArgumentError('Native manifest and digest must be supplied together.')
        if args.native_manifest is not None and (not Path(args.native_manifest).is_absolute()
                or re.fullmatch('[0-9a-f]{64}', args.native_manifest_digest) is None):
            raise ArgumentError('Native manifest requires an absolute path and lowercase SHA256 digest.')
        record = run_scan(Path.cwd(), all_scope=args.all, legacy_mode=args.legacy_mode,
                          native_manifest=args.native_manifest, native_manifest_digest=args.native_manifest_digest,
                          security=args.security)
        return attach_reports(record, record, repo_root=Path.cwd(),
                              formats=None if args.report_format is None else tuple(dict.fromkeys(args.report_format)))
    return result(args.command, complete=False, data=data,
                  errors=[{'code': 'CAPABILITY_UNAVAILABLE',
                           'message': 'The requested capability is unavailable in this invocation; '
                                      'no analysis or source verification was performed.'}])


def main(argv: list[str] | None = None) -> int:
    try:
        record = run(parser().parse_args(argv))
    except ArgumentError as error:
        record = misuse(str(error))
        print(json.dumps(record, ensure_ascii=True, sort_keys=True), file=sys.stderr)
        return record['exit_code']
    print(json.dumps(record, ensure_ascii=True, sort_keys=True))
    return record['exit_code']
