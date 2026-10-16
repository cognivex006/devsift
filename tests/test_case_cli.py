"""Actual case-prompt CLI pipeline; imported scan JSON never grants authority."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from devsift.evidence import Region, verify_source
from devsift.output import result

ROOT=Path(__file__).resolve().parents[1]


class CaseCliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.project=self.home/'project';self.project.mkdir()
        self.git('init','-q');self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        self.code="const endpoint='https://service.example.test';\n"
        (self.project/'client.ts').write_bytes(self.code.encode())
        self.git('add','client.ts');self.git('-c','commit.gpgsign=false','commit','-qm','fixture')
        self.sha=self.git('rev-parse','HEAD')
        source=verify_source(self.project,'fixture/repo',self.sha,'client.ts',Region(1,1,1,len(self.code.rstrip())+1))
        item={'case_id':'CASE-CLI','rule_id':'HC001','message':'untrusted message','path':'client.ts',
              'source':source.to_dict(),'severity':'Error','lifecycle_class':'UNKNOWN',
              'enforcement':'incomplete','security_escalation':False}
        self.record=result('scan',complete=False,findings=[item])
        self.input=self.home/'scan.json';self.input.write_text(json.dumps(self.record),encoding='utf-8')

    def git(self,*args):
        return subprocess.run(['git','-C',str(self.project),*args],check=True,capture_output=True,text=True).stdout.strip()

    def invoke(self,*args,path_override=None):
        environment=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE='1')
        if path_override is not None:environment['PATH']=path_override
        return subprocess.run([sys.executable,'-P','-B','-m','devsift','prompt',*args],cwd=self.project,
                              env=environment,
                              text=True,capture_output=True,timeout=30)

    def snapshot(self):
        return {str(p.relative_to(self.home)):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}

    def test_review_returns_source_bound_prompt_without_writes(self):
        before=self.snapshot();process=self.invoke('CASE-CLI','--mode','review','--scan-input',str(self.input))
        self.assertEqual(process.returncode,0,process.stderr+process.stdout)
        data=json.loads(process.stdout)['data'];prompt=data['prompt']
        self.assertEqual(prompt['source_sha'],self.sha)
        self.assertEqual(prompt['source']['status'],'VERIFIED')
        self.assertEqual(prompt['assessment']['lifecycle_class'],'UNKNOWN')
        self.assertFalse(prompt['writes_authorized']);self.assertFalse(prompt['automatic_fix'])
        self.assertEqual(prompt['commands'],[])
        self.assertEqual(self.snapshot(),before)

    def test_missing_source_withholds_path_patch_and_complete(self):
        item=self.record['findings'][0];item['source']['location']['source_sha']='a'*40
        self.input.write_text(json.dumps(self.record),encoding='utf-8')
        process=self.invoke('CASE-CLI','--mode','review','--scan-input',str(self.input))
        self.assertEqual(process.returncode,2,process.stderr)
        prompt=json.loads(process.stdout)['data']['prompt']
        self.assertEqual(prompt['source']['status'],'SOURCE_UNRESOLVED')
        self.assertIsNone(prompt['source']['location']);self.assertIsNone(prompt['after_proposal']['code'])

    def test_matching_operator_record_only_permits_manual_planning(self):
        args=('CASE-CLI','--mode','implement','--approved-case','CASE-CLI','--scan-input',str(self.input))
        first=self.invoke(*args);self.assertEqual(first.returncode,2,first.stderr+first.stdout)
        data=json.loads(first.stdout)['data'];prompt=data['prompt']
        now=datetime.now(timezone.utc)
        approval={'case_id':'CASE-CLI','source_sha':self.sha,'fingerprint':prompt['fingerprint'],
                  'prompt_digest':data['prompt_digest'],'mode':'implement','approved':True,'actor':'operator',
                  'issued_at':(now-timedelta(minutes=1)).isoformat(),'expires_at':(now+timedelta(hours=1)).isoformat()}
        path=self.home/'approval.json';path.write_text(json.dumps(approval),encoding='utf-8')
        before=self.snapshot();process=self.invoke(*args,'--approval-file',str(path))
        self.assertEqual(process.returncode,2,process.stderr+process.stdout)
        decision=json.loads(process.stdout)['data']['approval']
        self.assertTrue(decision['manual_planning_allowed'])
        self.assertEqual(decision['status'],'review_required')
        for key in ['writes_authorized','execution_authorized','automatic_fix']:self.assertFalse(decision[key])
        self.assertEqual(self.snapshot(),before)
        (self.project/'client.ts').write_text('changed_source();\n',encoding='utf-8')
        denied=self.invoke(*args,'--approval-file',str(path))
        self.assertEqual(denied.returncode,2,denied.stderr)
        self.assertFalse(json.loads(denied.stdout)['data']['approval']['manual_planning_allowed'])

    def test_unknown_case_malformed_input_and_duplicates_do_not_echo(self):
        process=self.invoke('privateWrongCase','--mode','review','--scan-input',str(self.input))
        self.assertEqual(process.returncode,2,process.stderr)
        self.assertNotIn('privateWrongCase',process.stdout+process.stderr)
        self.input.write_text('{"private":"privateInputValue","private":2}',encoding='utf-8')
        process=self.invoke('CASE-CLI','--mode','review','--scan-input',str(self.input))
        self.assertEqual(process.returncode,2,process.stderr)
        self.assertNotIn('privateInputValue',process.stdout+process.stderr)

    def test_consumer_git_executable_is_not_used_for_source_proof(self):
        shadow=self.project/('git.exe' if os.name=='nt' else 'git')
        if os.name=='nt':
            shadow.write_bytes(b'untrusted executable fixture, must never be selected')
        else:
            shadow.write_text('#!'+sys.executable+"\nfrom pathlib import Path\nPath('git-shadow-ran').write_text('bad')\nraise SystemExit(73)\n",encoding='utf-8')
            shadow.chmod(0o755)
        before=self.snapshot()
        process=self.invoke('CASE-CLI','--mode','review','--scan-input',str(self.input),
                            path_override=str(self.project)+os.pathsep+os.environ.get('PATH',''))
        self.assertEqual(process.returncode,0,process.stderr+process.stdout)
        self.assertFalse((self.project/'git-shadow-ran').exists())
        self.assertEqual(self.snapshot(),before)

    def test_source_mode_ignores_consumer_python_module_shadow(self):
        (self.project/'devsift.py').write_text("from pathlib import Path; Path('shadow-ran').write_text('bad'); raise SystemExit(73)",encoding='utf-8')
        process=self.invoke('CASE-CLI','--mode','review','--scan-input',str(self.input))
        self.assertEqual(process.returncode,0,process.stderr+process.stdout)
        self.assertFalse((self.project/'shadow-ran').exists())

    def test_approval_file_is_rejected_for_review_mode(self):
        process=self.invoke('CASE-CLI','--mode','review','--scan-input',str(self.input),'--approval-file',str(self.home/'approval.json'))
        self.assertEqual(process.returncode,3,process.stdout)
        self.assertEqual(json.loads(process.stderr)['status'],'misuse')


if __name__=='__main__':unittest.main()
