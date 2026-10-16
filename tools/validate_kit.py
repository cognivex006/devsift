#!/usr/bin/env python3
"""Offline safety/integrity checks for the DevSift v6 starter kit. No network or writes."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
MANDATORY=['README.md','AGENTS.md','DEVELOPMENT.md','CHANGELOG.md','CONTRIBUTING.md','SECURITY.md','.gitignore','.github/workflows/plan-validation.yml','docs/BOOTSTRAP-AUTOPILOT.md','plan/ledger.json','plan/MANIFEST.json','plan/goals/G000.md','plan/tasks/T000.md','plan/tasks/T076.md','tools/planctl.py','tools/validate_kit.py','tools/bootstrap_repo.py','docs/SPEC-V6.md','tests/test_planctl.py','skills/devsift/SKILL.md']
def main():
    missing=[p for p in MANDATORY if not (ROOT/p).is_file()]
    ledger=json.loads((ROOT/'plan/ledger.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'plan/MANIFEST.json').read_text(encoding='utf-8'))
    errors=[]
    if missing:errors.append('missing files: '+str(missing))
    if ledger.get('repository')!='orchex006/devsift':errors.append('incorrect repository')
    if len(ledger['goals'])!=manifest['goals'] or len(ledger['tasks'])!=manifest['tasks']:errors.append('manifest counts mismatch')
    for gid,g in ledger['goals'].items():
        if not (ROOT/'plan/goals'/f'{gid}.md').is_file():errors.append('missing goal card '+gid)
        if not all((ROOT/'plan/tasks'/f'{tid}.md').is_file() for tid in g['task_ids']):errors.append('missing task card '+gid)
    if any(p.is_file() for p in (ROOT/'plan/checkpoints').glob('*')):errors.append('checkpoint files must not ship')
    if errors:
        print('FAILED: '+'; '.join(errors),file=sys.stderr);return 1
    print(f'VALID: DevSift kit, {len(ledger["goals"])} goals / {len(ledger["tasks"])} tasks, {len(MANDATORY)} mandatory files');return 0
if __name__=='__main__':sys.exit(main())
