#!/usr/bin/env python3
"""Guarded DevSift empty-repo bootstrap CLI. Dry-run by default; never force pushes.

Run ONLY for T000 by an owner-authorized operator, in a clean extracted devsift/
kit root. This tool does not grant permissions and requires gh/git to be installed.
"""
from __future__ import annotations
import argparse, pathlib, shutil, subprocess, json, sys, hashlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
REPO='orchex006/devsift'
DESCRIPTION='DevSift is a language-agnostic code quality toolkit for change-aware analysis, source-linked diagnostics, risk-aware remediation, and automated quality gates.'
PATHS=['README.md','AGENTS.md','DEVELOPMENT.md','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md','.editorconfig','.gitignore','.github','plan','docs','tools','tests','skills','governance','templates','prompts','reference','integration']

def run(*argv,check=True):
    p=subprocess.run(argv,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    if check and p.returncode:raise RuntimeError(f'{argv[0]} {argv[1] if len(argv)>1 else ""} failed ({p.returncode}): {p.stderr.strip()[:450]}')
    return p

def preflight():
    if shutil.which('git') is None or shutil.which('gh') is None:raise RuntimeError('git and authenticated gh CLI required')
    if (ROOT/'.git').exists():raise RuntimeError('Refuse bootstrap from existing Git repo: no implicit history overwrite')
    for p in PATHS:
        if not (ROOT/p).exists():raise RuntimeError(f'Missing approved bootstrap path: {p}')
    from_plan=run(sys.executable,str(ROOT/'tools/planctl.py'),'validate')
    from_kit=run(sys.executable,str(ROOT/'tools/validate_kit.py'))
    run(sys.executable,'-m','unittest','discover','-s','tests','-v')
    run('gh','auth','status')
    meta=json.loads(run('gh','api',f'repos/{REPO}').stdout)
    if meta.get('full_name')!=REPO or meta.get('private') is not False:raise RuntimeError('Repository identity/visibility mismatch')
    refs=run('git','ls-remote','--heads','--tags',f'https://github.com/{REPO}.git')
    if refs.stdout.strip():raise RuntimeError('Repository has refs; cannot perform empty-only initialization')
    if any((ROOT/'plan/checkpoints').glob('*')):raise RuntimeError('Generated checkpoints must not be published')
    manifest=[]
    for base in PATHS:
        path=ROOT/base
        for f in ([path] if path.is_file() else path.rglob('*')):
            if not f.is_file() or '__pycache__' in f.parts or f.suffix in ('.pyc','.pyo') or '.git' in f.parts:continue
            manifest.append((f.relative_to(ROOT).as_posix(),hashlib.sha256(f.read_bytes()).hexdigest()))
    if not manifest:raise RuntimeError('Source manifest empty')
    print(f'PRECHECK OK: {REPO} remote empty; {len(manifest)} publishable files; local plan/tests validated. GitHub description currently: {meta.get("description")!r}')
    return manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--apply',action='store_true',help='Perform initial git commit/push and repo description write. Requires --confirm-repo')
    ap.add_argument('--confirm-repo',default='',help='Must exactly match orchex006/devsift')
    args=ap.parse_args()
    try:
        manifest=preflight()
        if not args.apply:
            print('DRY RUN ONLY. Nothing written to GitHub. Execute with --apply --confirm-repo orchex006/devsift only after scoped approval.');return 0
        if args.confirm_repo!=REPO:raise RuntimeError('Missing exact --confirm-repo owner/name')
        run('git','init','-b','main')
        run('git','remote','add','origin',f'https://github.com/{REPO}.git')
        run('git','add','--',*PATHS)
        run('git','diff','--cached','--check')
        listed=set(run('git','diff','--cached','--name-only').stdout.strip().splitlines())
        expected={f for f,_ in manifest}
        if listed!=expected:
            raise RuntimeError(f'Staged tree differs from exact manifest: missing={sorted(expected-listed)[:10]}, extra={sorted(listed-expected)[:10]}')
        # Second remote race check before commit/push. Push still rejects non-fast-forward.
        if run('git','ls-remote','--heads','--tags',f'https://github.com/{REPO}.git').stdout.strip():
            raise RuntimeError('Remote refs appeared before push; stop without replacing history')
        run('git','commit','-m','chore(repo): bootstrap DevSift governance and execution kit','-m','Refs: T000')
        sha=run('git','rev-parse','HEAD').stdout.strip()
        run('git','push','-u','origin','main')
        # A failed description update after pushing is intentionally explicit and recoverable.
        run('gh','repo','edit',REPO,'--description',DESCRIPTION)
        remote_sha=run('git','ls-remote','origin','refs/heads/main').stdout.split()[0]
        desc=json.loads(run('gh','api',f'repos/{REPO}').stdout).get('description')
        if remote_sha!=sha or desc!=DESCRIPTION:raise RuntimeError(f'Remote verification mismatch: expected sha={sha} remote={remote_sha} description={desc!r}')
        print(f'BOOTSTRAPPED {REPO} commit={sha} files={len(expected)} description_verified=true. Independent review still required for T000 acceptance.')
        return 0
    except Exception as e:
        print('BOOTSTRAP HALTED:',e,file=sys.stderr)
        print('If commit/push already succeeded, NEVER force rerun; verify remote SHA and finish metadata via gh repo edit before independent review.',file=sys.stderr)
        return 2
if __name__=='__main__':sys.exit(main())
