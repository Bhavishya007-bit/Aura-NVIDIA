"""Apply the documented Ultra profile locally without exposing or replacing keys."""
import argparse
import os
from pathlib import Path
import re
import tempfile

from dotenv import dotenv_values
import requests

MODEL = 'nvidia/Nemotron-3-Ultra-550b-a55b'
PROFILE = {
    'NEBIUS_BASE_URL': 'https://api.tokenfactory.us-central1.nebius.com/v1',
    'NEBIUS_MODEL': MODEL,
    'NEBIUS_COVERAGE_MODEL': MODEL,
    'NEBIUS_ANSWER_MODEL': MODEL,
    'NEBIUS_DEEP_MODEL': MODEL,
    'NEBIUS_MAX_TOKENS': '16384',
    'NEBIUS_JSON_MAX_TOKENS': '16384',
    'NEBIUS_READ_TIMEOUT': '180',
    'AURA_MAX_ANSWER_TOKENS': '32768',
    'NEBIUS_SUMMARY_REASONING_EFFORT': 'none',
    'NEBIUS_VERIFICATION_REASONING_EFFORT': 'none',
    'AURA_SUMMARY_BACKGROUND': 'true',
    'AURA_SUMMARY_EXPANSION_SECONDS': '300',
    'AURA_SUMMARY_REPAIRS': '6',
}


def apply_profile(path):
    original = path.read_text(encoding='utf-8')
    lines, found = [], set()
    for line in original.splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=', line)
        key = match[1] if match else None
        if key in PROFILE:
            # Replace all definitions, including duplicates, so the local
            # dotenv parser and shell do not disagree about the active value.
            lines.append(f'{key}={PROFILE[key]}')
            found.add(key)
        else:
            lines.append(line)
    lines += [f'{key}={value}' for key, value in PROFILE.items() if key not in found]
    handle, temporary = tempfile.mkstemp(prefix='.env.quality-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8', newline='\n') as output:
            output.write('\n'.join(lines) + '\n')
        os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def smoke_check(path):
    config = dotenv_values(path)
    key = os.environ.get('NEBIUS_API_KEY') or config.get('NEBIUS_API_KEY')
    if not key or key.startswith('replace_'):
        print('CHECK FAILED: set your existing NEBIUS_API_KEY locally. No key was printed.')
        return False
    try:
        reply = requests.post(PROFILE['NEBIUS_BASE_URL'] + '/chat/completions',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={'model': MODEL, 'messages': [{'role': 'user', 'content': 'Return JSON only: {"ok":true}'}],
                  'response_format': {'type': 'json_object'}, 'reasoning_effort': 'none',
                  'max_tokens': 256, 'temperature': 0}, timeout=(10, 45), allow_redirects=False)
        if reply.status_code != 200:
            print(f'CHECK FAILED: provider HTTP {reply.status_code}. Check model/project access in Token Factory; no automatic model downgrade was made.')
            return False
        import json
        choice = reply.json()['choices'][0]
        if choice.get('finish_reason') != 'stop' or json.loads(choice['message']['content']) != {'ok': True}:
            raise ValueError('Invalid smoke response')
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        print('CHECK FAILED: the model connection or JSON response could not be validated. No private response was printed.')
        return False
    print('OK: Nemotron Ultra returned valid JSON with the configured output controls.')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Update backend/.env; keep keys and database settings.')
    parser.add_argument('--smoke', action='store_true', help='Make one small paid synthetic request, without student material.')
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / 'backend' / '.env'
    if args.apply and not path.is_file():
        parser.error('Create backend/.env using the existing setup first.')
    # Validate access before replacing a working configuration when both flags
    # are supplied. An unavailable model must leave the old settings intact.
    if args.smoke and not smoke_check(path):
        raise SystemExit(1)
    if args.apply:
        apply_profile(path)
        print('Applied the Ultra quality profile. Keys and database settings were kept. Restart FastAPI.')
        print('Existing shell environment variables take precedence over backend/.env.')
    if not args.apply and not args.smoke:
        print('Profile: Nemotron Ultra for coverage, answers and deep reasoning; larger output allowances.')
        print('Use --apply to update local configuration. --smoke optionally tests one small paid request.')


if __name__ == '__main__':
    main()
