"""Explicit production-Python CI scan and outside-source report bundle."""
from pathlib import Path, PurePosixPath
import sys

KIT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT_ROOT))  # Never import the --repo target package.

import argparse
import os
import re

from devsift.ci_artifacts import annotation_lines, build_reports, write_report_bundle
from devsift.ci_gate import GateConfig, run_ci
from devsift.cli_scan import _git


class UsageError(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError('Invalid quality pipeline arguments') from None


def main(argv=None):
    parser = Parser(description='Analyze tracked production Python; write reports outside source.', allow_abbrev=False)
    parser.add_argument('--repo', default=str(KIT_ROOT), help='Explicit target Git root; default is this trusted kit.')
    parser.add_argument('--output', required=True, help='Absolute outside-source destination for three new reports.')
    parser.add_argument('--base', help='Full nonzero 40-hex commit; otherwise use DEVSIFT_BASE_SHA.')
    try:
        args = parser.parse_args(argv)
        base = args.base if args.base is not None else os.environ.get('DEVSIFT_BASE_SHA') or None
        if base is not None:
            if re.fullmatch('[0-9a-fA-F]{40}', base) is None or base == '0' * 40:
                raise UsageError('Invalid comparison commit')
            base = base.lower()
        output = Path(args.output)
        if not output.is_absolute():
            raise UsageError('Absolute output required')
        root = Path(args.repo).resolve(strict=True)
        if output.resolve().is_relative_to(root):
            raise UsageError('Outside-source output required')
        if any((output / name).exists() or (output / name).is_symlink()
               for name in ('report.md', 'findings.json', 'results.sarif')):
            raise UsageError('Existing report destination')
        manifest = KIT_ROOT / '.devsift/local/native-manifest.json'
        with (KIT_ROOT / '.devsift/local/native-manifest.sha256').open('rb') as stream:
            digest_bytes = stream.read(130)
        digest = digest_bytes.decode('ascii').strip()
        if len(digest_bytes) > 129 or re.fullmatch('[0-9a-f]{64}', digest) is None:
            raise ValueError('Trusted manifest unavailable')
        paths = []
        # _git uses literal pathspecs: select directory, then exact top-level .py.
        for raw in _git(root, 'ls-files', '-z', '--', 'devsift').split(b'\0'):
            if raw:
                value = raw.decode('utf-8')
                path = PurePosixPath(value)
                if len(path.parts) == 2 and path.parts[0] == 'devsift' and path.suffix == '.py':
                    paths.append(value)
        paths = tuple(sorted(set(paths)))
        config = GateConfig()
        run = run_ci(root, native_manifest=manifest, native_manifest_digest=digest,
                     base_ref=base, paths=paths, security=True, config=config)
        record = run.scan_record()
        if run.exit_code == 2 and record['complete']:
            # Independent review may make CI incomplete after a completed scan.
            record.update(complete=False, status='incomplete', exit_code=2)
            record['errors'].append({'code': 'CI_GATE_INCOMPLETE',
                                     'message': 'The authoritative CI gate requires further review.'})
        report, _ = build_reports(record, repo_root=root, trusted_lifecycles=True, policy=config.policy())
        write_report_bundle(report, repo_root=root, destination=output)
        for line in annotation_lines(report):
            print(line)
        print(f'::notice::DevSift quality reports generated for {len(paths)} explicit tracked production Python files; native probes are not whole-repository coverage.')
        if run.exit_code == 2 or not report.complete:
            return 2
        return max(run.exit_code, report.exit_code)
    except UsageError:
        print('DevSift quality pipeline arguments are invalid.', file=sys.stderr)
        return 3
    except Exception:
        print('::error::DevSift quality pipeline incomplete; trusted setup, source or report artifacts are unavailable.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
