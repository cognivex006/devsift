"""Strict, read-only CLI. Analyzer/report integration is deliberately incomplete."""
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
    root = Parser(prog='devsift', description='Read-only scan coordination (native analyzers pending).')
    commands = root.add_subparsers(dest='command', required=True)
    scan = commands.add_parser('scan', help='Inventory targets; native analyzers are not registered yet.')
    scope = scan.add_mutually_exclusive_group()
    scope.add_argument('--changed', action='store_true', help='Inventory staged, unstaged and untracked working-tree paths (default).')
    scope.add_argument('--all', action='store_true', help='Include legacy source as recommendations.')
    scan.add_argument('--legacy-mode', choices=['recommend'], default='recommend',
                      help='Untouched legacy is advisory; no bulk remediation.')
    scan.add_argument('--native-manifest', help='Absolute explicitly trusted native tool manifest; authorizes code execution.')
    scan.add_argument('--native-manifest-digest', help='Independently trusted SHA256 of the exact manifest bytes.')
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
    elif args.command == 'scan':
        from pathlib import Path
        import re
        from .cli_scan import run_scan
        if (args.native_manifest is None) != (args.native_manifest_digest is None):
            raise ArgumentError('Native manifest and digest must be supplied together.')
        if args.native_manifest is not None and (not Path(args.native_manifest).is_absolute()
                or re.fullmatch('[0-9a-f]{64}', args.native_manifest_digest) is None):
            raise ArgumentError('Native manifest requires an absolute path and lowercase SHA256 digest.')
        return run_scan(Path.cwd(), all_scope=args.all, legacy_mode=args.legacy_mode,
                        native_manifest=args.native_manifest, native_manifest_digest=args.native_manifest_digest)
    return result(args.command, complete=False, data=data,
                  errors=[{'code': 'CAPABILITY_UNAVAILABLE',
                           'message': 'Analyzer and verified report backends are not implemented; '
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
