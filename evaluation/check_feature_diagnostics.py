"""Offline regression checks for account-scoped operator diagnostics."""
import contextvars
import importlib.util
import io
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('feature_check', ROOT/'scripts/check_features.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

class DiagnosticsTests(unittest.TestCase):
    def run_check(self, email=None, exists=True, blocked=False):
        actor = contextvars.ContextVar('test_actor', default=None)
        calls = []
        queries = []
        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def execute(self, sql, params): queries.append((sql, params))
            def fetchone(self):
                return ((42,) if exists else None) if 'student_id' in queries[-1][0] else ('table',)
        class Connection:
            def cursor(self): return Cursor()
            def close(self): pass
        class Blocked(Exception):
            detail = {'code': 'ai_paused', 'message': 'not printed'}
        class LLM:
            def for_task(self, task): self.task=task;return self
            def for_summary(self): return self
            def with_output_budget(self,*args,**kwargs): return self
            def generate_json(self,*args,**kwargs):
                assert actor.get() == 42
                calls.append(self.task)
                if blocked: raise Blocked()
                return {'ok':True}
        modules = {}
        for name,attrs in {
            'backend.auth_db': {'get_auth_connection':Connection},
            'backend.production.config': {'enabled':lambda:True},
            'backend.production.limits': {'actor':actor},
            'backend.ai.llm': {'LLM':LLM},
        }.items():
            m=ModuleType(name);m.__dict__.update(attrs);modules[name]=m
        response=io.StringIO(__import__('json').dumps({'paths':dict.fromkeys(('/auth/register','/agents/memory','/agents/tasks','/agents/runs','/study/tools','/study/capabilities'),{})}))
        output=io.StringIO()
        argv=['check_features','--live']+(['--account-email',email] if email else [])
        with patch.dict(sys.modules,modules), patch.object(sys,'argv',argv), patch.object(check.urllib.request,'urlopen',return_value=response), redirect_stdout(output):
            result=check.main()
        self.assertIsNone(actor.get())
        return result,output.getvalue(),calls,queries

    def test_production_requires_explicit_account(self):
        status,output,calls,_=self.run_check()
        self.assertEqual(status,1);self.assertIn('--account-email',output);self.assertEqual(calls,[])

    def test_unknown_account_cannot_call_provider(self):
        status,output,calls,_=self.run_check('missing@example.test',exists=False)
        self.assertEqual(status,1);self.assertIn('Account not found',output);self.assertEqual(calls,[])

    def test_scoped_requests_restore_context(self):
        status,output,calls,queries=self.run_check('personal@example.test')
        self.assertEqual(status,0);self.assertEqual(calls,['coverage','answer','deep'])
        self.assertNotIn('personal@example.test',output)
        self.assertIn(('personal@example.test',),[params for sql,params in queries if 'student_id' in sql])

    def test_pause_controls_still_report_failure(self):
        status,output,_,_=self.run_check('personal@example.test',blocked=True)
        self.assertEqual(status,1);self.assertIn('paused by deployment controls',output)

if __name__=='__main__': unittest.main()
