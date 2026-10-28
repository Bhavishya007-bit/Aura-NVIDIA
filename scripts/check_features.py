"""Read-only setup checks. --live makes three small real provider requests."""
import argparse
import json
import os
import urllib.request
from pathlib import Path
import sys

# Support both python scripts/name.py and python -m scripts.name.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TABLES = ('students','courses','sources','chunks','aura_memories','aura_memory_settings','aura_agent_tasks','aura_agent_runs','aura_study_artifacts','aura_study_attempts','aura_generation_jobs','aura_card_reviews','aura_study_activity')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    failed=False
    try:
        from backend.auth_db import get_auth_connection
        con=get_auth_connection()
        try:
            with con.cursor() as cur:
                for name in TABLES:
                    cur.execute('SELECT to_regclass(%s)',('public.'+name,))
                    present=cur.fetchone()[0] is not None
                    print(('OK' if present else 'MISSING')+': '+name)
                    failed |= not present
        finally:con.close()
    except Exception as error:
        print('FAILED: database connection/schema check ('+type(error).__name__+').');failed=True
    try:
        base='http://127.0.0.1:'+os.getenv('PORT','8000')
        with urllib.request.urlopen(base+'/openapi.json',timeout=10) as response:
            routes=json.load(response)['paths']
        for path in ('/auth/register','/agents/memory','/agents/tasks','/agents/runs','/study/tools','/study/capabilities'):
            present=path in routes
            print(('OK' if present else 'MISSING')+': route '+path);failed |= not present
    except Exception as error:
        print('FAILED: running API route check ('+type(error).__name__+').');failed=True
    if args.live:
        from backend.ai.llm import LLM
        for task in ('coverage','answer','deep'):
            try:
                client=LLM().for_task(task).for_summary().with_output_budget(1024,exact=True)
                value=client.generate_json('Return only the JSON object {"ok":true}. This is a setup connectivity check.',max_retries=1)
                if value.get('ok') is not True:raise ValueError('Unexpected check result')
                print('OK: '+task+' model JSON request')
            except Exception as error:
                print('FAILED: '+task+' model request ('+type(error).__name__+'). Check the provider warning above; do not share your key.');failed=True
    print('Setup checks '+('FAILED. Fix the reported section before retrying generation.' if failed else 'passed. Real document generation and account-specific actions still need a UI check.'))
    return 1 if failed else 0

if __name__=='__main__':raise SystemExit(main())
