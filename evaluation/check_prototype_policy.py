"""Offline prototype policy checks: no provider calls or real database access."""
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from backend.production import limits
from backend.study_v2 import budget
from backend.ai.llm import LLM
from scripts.configure_model_quality import apply_profile, PROFILE, MODEL
from dotenv import dotenv_values

class Cursor:
    def __init__(self): self.calls=[]
    def execute(self,sql,params=None): self.calls.append((sql,params))
    def fetchone(self):
        sql=self.calls[-1][0]
        if 'ai_enabled' in sql:return {'ai_enabled':True}
        return {'used_tokens':10**9,'reserved_tokens':10**9,'day':date(2026,10,29)}

class PrototypePolicy(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'AURA_ENV':'production'},clear=True);self.env.start()
        self.cursor=Cursor()
        @contextmanager
        def db(): yield self.cursor
        self.patches=[patch.object(limits,'db',db),patch.object(budget,'db',db)]
        for p in self.patches:p.start()
        self.actor=limits.actor.set(42)
        self.job=budget.current.set(('fixture',42))
    def tearDown(self):
        budget.current.reset(self.job);limits.actor.reset(self.actor)
        for p in self.patches:p.stop()
        self.env.stop()
    def test_prototype_ignores_old_daily_totals_but_records_usage(self):
        reservation=limits.reserve({'messages':[],'max_tokens':100})
        limits.settle(reservation,{'prompt_tokens':10,'completion_tokens':5})
        self.assertEqual(reservation[0],42)
        self.assertTrue(any('used_tokens=used_tokens+' in sql for sql,params in self.cursor.calls))
    def test_study_generation_ignores_old_totals_but_settles_usage(self):
        reservation=budget.reserve(100)
        budget.settle(reservation,{'prompt_tokens':10,'completion_tokens':5})
        self.assertEqual(reservation[0],42)
        self.assertTrue(any('used_tokens=used_tokens+' in sql for sql,params in self.cursor.calls))
    def test_daily_enforcement_can_be_explicitly_restored(self):
        with patch.dict(os.environ,{'AURA_DAILY_LIMITS_ENABLED':'true'}):
            for call in (lambda: limits.reserve({'max_tokens':100}),lambda: budget.reserve(100)):
                with self.assertRaises(HTTPException) as caught:call()
                self.assertEqual(caught.exception.status_code,429)
    def test_ai_pause_still_blocks_when_daily_limits_are_off(self):
        with patch.dict(os.environ,{'AURA_AI_ENABLED':'false'}):
            with self.assertRaises(HTTPException) as caught:limits.reserve({'max_tokens':100})
            self.assertEqual(caught.exception.detail['code'],'ai_paused')
    def test_account_context_is_still_required(self):
        a=limits.actor.set(None);j=budget.current.set(None)
        try:
            with self.assertRaises(HTTPException) as caught:limits.reserve({'max_tokens':100})
            self.assertEqual(caught.exception.detail['code'],'unscoped_generation')
        finally:budget.current.reset(j);limits.actor.reset(a)
    def test_existing_native_configuration_selects_ultra_and_preserves_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'.env'
            path.write_text('NEBIUS_API_KEY=synthetic-secret\nDB_PASSWORD=synthetic-db\nNEBIUS_MODEL=old\nAURA_DAILY_LIMITS_ENABLED=true\n')
            apply_profile(path)
            settings=dotenv_values(path)
            self.assertEqual(settings['NEBIUS_API_KEY'],'synthetic-secret')
            self.assertEqual(settings['DB_PASSWORD'],'synthetic-db')
            self.assertEqual(settings['AURA_DAILY_LIMITS_ENABLED'],'false')
            with patch.dict(os.environ,{**settings},clear=True):
                for task in ('coverage','answer','deep'):
                    self.assertEqual(LLM().for_task(task).model_name,MODEL)

if __name__=='__main__':unittest.main()
