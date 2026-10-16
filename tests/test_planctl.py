import sys,json,copy,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from planctl import load,evaluate
class Classification(unittest.TestCase):
 def p(self,goals,deps):
  return {'goals':{g:{'task_ids':v} for g,v in goals.items()},'tasks':{t:{'goal_id':g,'depends_on':deps.get(t,[]),'status':'pending'} for g,ids in goals.items() for t in ids}}
 def test_partial_dependency_is_a(self):
  p=self.p({'G001':['T001','T002'],'G002':['T003']},{'T003':['T001']}); self.assertEqual(evaluate(p)[0]['G002']['class'],'A')
 def test_all_predecessor_tasks_is_b(self):
  p=self.p({'G001':['T001','T002'],'G002':['T003']},{'T003':['T001','T002']});self.assertEqual(evaluate(p)[0]['G002']['class'],'B')
 def test_two_independent_gates_b_but_path_ready_separately(self):
  p=self.p({'G001':['T001'],'G002':['T002'],'G003':['T003','T004']},{'T003':['T001'],'T004':['T002']});p['tasks']['T001']['status']='accepted';r=evaluate(p)[0]['G003'];self.assertEqual(r['class'],'B');self.assertTrue(r['entry_paths'][0]['ready']);self.assertFalse(r['entry_paths'][1]['ready'])
 def test_mixed_entries_a(self):
  p=self.p({'G001':['T001','T002'],'G002':['T003','T004']},{'T003':['T001'],'T004':['T001','T002']});self.assertEqual(evaluate(p)[0]['G002']['class'],'A')
 def test_cycle_rejected(self):
  p=self.p({'G001':['T001','T002']},{'T001':['T002'],'T002':['T001']});self.assertRaisesRegex(ValueError,'cycle',evaluate,p)
 def test_missing_rejected(self):
  p=self.p({'G001':['T001']},{'T001':['T999']});self.assertRaisesRegex(ValueError,'missing',evaluate,p)
 def test_readiness_does_not_change_class(self):
  p=self.p({'G001':['T001'],'G002':['T002']},{'T002':['T001']});r1=evaluate(p)[0]['G002'];p['tasks']['T001']['status']='accepted';r2=evaluate(p)[0]['G002'];self.assertEqual(r1['class'],r2['class']);self.assertFalse(r1['entry_paths'][0]['ready']);self.assertTrue(r2['entry_paths'][0]['ready'])
 def test_bootstrap_is_only_initial_ready_task(self):
  p=load()
  for task in p['tasks'].values():task['status']='pending'
  r,_=evaluate(p)
  ready=[t for t,x in p['tasks'].items() if x['status']=='pending' and all(p['tasks'][d]['status']=='accepted' for d in x['depends_on'])]
  self.assertEqual(ready,['T000'])
  self.assertEqual(r['G000']['execution_id'],'GA000')
 def test_partial_bootstrap_acceptance_unlocks_without_goal_complete(self):
  p=load()
  for task in p['tasks'].values():task['status']='pending'
  p['tasks']['T000']['status']='accepted'
  r,_=evaluate(p)
  self.assertFalse(r['G000']['goal_complete'])
  ready=[t for t,x in p['tasks'].items() if x['status']=='pending' and all(p['tasks'][d]['status']=='accepted' for d in x['depends_on'])]
  self.assertEqual(set(ready),{'T076','T001','T002','T004','T005','T007','T008'})
  self.assertEqual(r['G001']['class'],'A')
 def test_full_plan(self):
  p=load();r,_=evaluate(p);self.assertEqual(len(p['goals']),26);self.assertEqual(len(p['tasks']),77);self.assertTrue(any(x['class']=='A' for x in r.values()));self.assertTrue(any(x['class']=='B' for x in r.values()))
if __name__=='__main__':unittest.main()
