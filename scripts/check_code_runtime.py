"""Check execution setup without an LLM, database connection or secret output.

Default: read-only local Docker image check (no cloud requests). --smoke runs a
fixed, authored CSV calculation through the configured isolation backend.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
from backend.agents import sandbox


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true', help='Run one fixed program inside the configured backend; Nebius may charge for this operation.')
    args = parser.parse_args(argv)
    load_dotenv(ROOT / 'backend' / '.env')
    mode = os.getenv('AURA_CODE_BACKEND', 'disabled').strip().lower()
    try:
        if mode == 'docker':
            client = sandbox.docker_executable()
            print('Docker client selection: ' + ('native .exe' if client and client.lower().endswith('.exe') else 'POSIX executable' if client and sys.platform != 'win32' else 'unavailable'))
            expected = os.getenv('AURA_DOCKER_IMAGE', 'aura-code:1') == 'aura-code:1'
            print('Configured image: ' + ('aura-code:1' if expected else 'custom image (check AURA_DOCKER_IMAGE in backend/.env)'))
            sandbox.inspect_docker_image()
            print('Docker connection and prepared Linux image: OK')
        elif mode == 'nebius' and sandbox.backend_name() == 'nebius':
            print('Nebius configuration format: OK (access and image have not been checked)')
        else:
            raise sandbox.SandboxUnavailable('not_configured')
        if not args.smoke:
            print('No code was executed. To test execution, run: python scripts/check_code_runtime.py --smoke')
            return 0
        # No model, supplied code, package install, host-code path or network in the guest.
        program = "import csv, json, statistics\nwith open('input.csv') as f: values=[float(row['value']) for row in csv.DictReader(f)]\nmean=statistics.mean(values)\nassert mean == 4\nprint('Aura sandbox OK: mean =', mean)\nwith open('result.json', 'w') as f: json.dump({'mean':mean},f)"
        result = sandbox.execute(program, ['result.json'], {'input.csv': 'value\n2\n6\n'},
            run_id=uuid4(), attempt=1, seconds=30, check_active=lambda: None, on_start=lambda handle: None)
        if result['status'] != 'succeeded' or result['missing_outputs']:
            raise sandbox.SandboxUnavailable('invalid_result')
        artifact = next((item for item in result['artifacts'] if item['name'] == 'result.json'), None)
        import base64
        if artifact is None or json.loads(base64.b64decode(artifact['data'])) != {'mean': 4}:
            raise sandbox.SandboxUnavailable('invalid_result')
        print('Isolated Python execution and CSV output check: OK')
        return 0
    except sandbox.SandboxUnavailable as error:
        print('CHECK FAILED: ' + sandbox.FAILURE_MESSAGES[error.code])
        print('Technical reason: ' + error.code)
        if error.diagnostics:
            print('Diagnostic details: ' + json.dumps(error.diagnostics, sort_keys=True))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
