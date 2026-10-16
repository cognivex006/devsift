#!/usr/bin/env python3
"""Read-only by default: exact task-DAG A/B classification and frontier.
A checkpoint command writes only to plan/checkpoints/, never changes source code.
"""
from __future__ import annotations
import argparse,json,sys,pathlib,datetime,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
def load(path=None):return json.loads((pathlib.Path(path) if path else ROOT/'plan/ledger.json').read_text(encoding='utf-8'))
def evaluate(p):
    tasks=p['tasks'];goals=p['goals'];missing=[];cycles=[];visited={};top=[]
    for tid,t in tasks.items():
        if t['goal_id'] not in goals:missing.append(f'{tid}:missing-goal:{t["goal_id"]}')
        for d in t['depends_on']:
            if d not in tasks:missing.append(f'{tid}:missing-task:{d}')
    for gid,g in goals.items():
        for tid in g['task_ids']:
            if tid not in tasks:missing.append(f'{gid}:missing-task:{tid}')
            elif tasks[tid]['goal_id']!=gid:missing.append(f'{gid}:wrong-owner:{tid}')
    if missing:raise ValueError('; '.join(missing))
    if sorted(t for g in goals.values() for t in g['task_ids'])!=sorted(tasks):raise ValueError('Duplicate or unowned task IDs')
    def dfs(n):
        if visited.get(n)==1:raise ValueError('dependency cycle at '+n)
        if visited.get(n)==2:return
        visited[n]=1
        for d in tasks[n]['depends_on']:dfs(d)
        visited[n]=2;top.append(n)
    for t in tasks:dfs(t)
    memo={}
    def prereq(t):
        if t not in memo:
            r=set()
            for d in tasks[t]['depends_on']:r.add(d);r|=prereq(d)
            memo[t]=r
        return memo[t]
    results={}
    for gid,g in goals.items():
        members=set(g['task_ids']);entries=[t for t in g['task_ids'] if not (prereq(t)&members)]
        if not entries:raise ValueError(f'{gid} no true entry tasks')
        paths=[]
        for tid in entries:
            prereqs=prereq(tid);gates=[];partials={}
            for pg,pgobj in goals.items():
                if pg==gid:continue
                intersect=prereqs&set(pgobj['task_ids'])
                if intersect==set(pgobj['task_ids']):gates.append(pg)
                elif intersect:partials[pg]=sorted(intersect)
            paths.append({'entry_task':tid,'all_transitive_prerequisites':sorted(prereqs),'full_goal_gates':sorted(gates),'partial_task_prerequisites':partials,'ready':all(tasks[d]['status']=='accepted' for d in prereqs),'blocking_tasks':sorted(d for d in prereqs if tasks[d]['status']!='accepted')})
        klass='B' if all(x['full_goal_gates'] for x in paths) else 'A'
        results[gid]={'canonical_id':gid,'execution_id':f'G{klass}{gid[1:]}','class':klass,'reason':'Every true entry has at least one full predecessor-goal gate' if klass=='B' else 'At least one true entry has no full predecessor-goal gate','entry_paths':paths,'goal_complete':all(tasks[t]['status']=='accepted' for t in members)}
    return results,top

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['validate','classify','frontier','status','checkpoint']);ap.add_argument('--ledger');ap.add_argument('--out'); args=ap.parse_args()
    p=load(args.ledger);r,top=evaluate(p)
    if args.command=='validate':
        print('VALID: '+str(len(p['goals']))+' goals / '+str(len(p['tasks']))+' tasks; DAG acyclic; refs resolved; A='+str(sum(x['class']=='A' for x in r.values()))+' B='+str(sum(x['class']=='B' for x in r.values())));return 0
    if args.command=='classify':print(json.dumps(r,indent=2));return 0
    if args.command=='frontier':
        ready=[{'task':tid,'goal':t['goal_id'],'execution_id':r[t['goal_id']]['execution_id'],'locks':t['resource_locks']} for tid,t in p['tasks'].items() if t['status']=='pending' and all(p['tasks'][d]['status']=='accepted' for d in t['depends_on'])]
        print(json.dumps({'ready':ready,'count':len(ready)},indent=2));return 0
    if args.command=='status':
        print(json.dumps({'counts':{s:sum(t['status']==s for t in p['tasks'].values()) for s in ['pending','claimed','running','in_review','accepted','blocked','paused','rework']},'class_counts':{k:sum(v['class']==k for v in r.values()) for k in 'AB'}},indent=2));return 0
    if args.command=='checkpoint':
        target=pathlib.Path(args.out) if args.out else ROOT/'plan/checkpoints/current.json';target.parent.mkdir(exist_ok=True,parents=True)
        state={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ledger_sha256':hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest(),'ledger':p,'classification':r,'ready_tasks':[t for t in top if p['tasks'][t]['status']=='pending' and all(p['tasks'][d]['status']=='accepted' for d in p['tasks'][t]['depends_on'])]}
        tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(state,indent=2,ensure_ascii=False));tmp.replace(target);print(target);return 0
if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,KeyError,FileNotFoundError) as e:print('INVALID:',e,file=sys.stderr);sys.exit(2)
