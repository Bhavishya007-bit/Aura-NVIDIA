"""Optional eight-call reviewer audit. Synthetic evidence only; never runs Python.

Fixture expectations are assistant-authored, not independent human calibration.
No code tools, revision requests, student data or database access are used.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from backend.agents.code_review import REVIEW_SYSTEM, Review, review_payload

DEFAULT_PACKET = 'evaluation/results/code_quality.json'
LABELS = ('supported', 'unsupported')

SEARCH = '''def linear(values, target):
    count = 0
    for i, value in enumerate(values):
        count += 1
        if value == target:
            return i, count
    return -1, count

def binary(values, target):
    lo, hi, count = 0, len(values)-1, 0
    while lo <= hi:
        mid = (lo+hi)//2
        count += 1
        if values[mid] == target:
            return mid, count
        if values[mid] < target:
            lo = mid+1
        else:
            hi = mid-1
    return -1, count

values = [2,5,8,12,16,23,38,42,50]
for target in [2,23,50,7]:
    li, lc = linear(values, target)
    bi, bc = binary(values, target)
    print(f'{target}: linear index={li}, probes={lc}; binary index={bi}, probes={bc}')
'''
SEARCH_STDOUT = ('2: linear index=0, probes=1; binary index=0, probes=3\n'
                 '23: linear index=5, probes=6; binary index=5, probes=3\n'
                 '50: linear index=8, probes=9; binary index=8, probes=4\n'
                 '7: linear index=-1, probes=9; binary index=-1, probes=3\n')
TIMING = SEARCH.split('values =')[0] + '''import time
values = [1,3,5,7,9,11,13,15]
start = time.perf_counter()
li, _ = linear(values, 7)
lt = time.perf_counter()-start
start = time.perf_counter()
bi, _ = binary(values, 7)
bt = time.perf_counter()-start
print(f'Linear index {li} ({lt:.2f}s), Binary index {bi} ({bt:.2f}s)')
'''


def cases():
    """Authored program/output pairs, not live sandbox executions or uploads."""
    table = '| Target | Linear probes | Binary probes |\n|---|---|---|\n|2|1|3|\n|23|6|3|\n|50|9|4|\n|7|9|3|\n'
    examples = [
        ('position-bad', SEARCH, SEARCH_STDOUT,
         'The sorted list [2,5,8,12,16,23,38,42,50].\n23 is the middle element.\n'+table+
         'The results confirm binary search uses fewer probes than linear search.', 'unsupported'),
        ('position-good', SEARCH, SEARCH_STDOUT,
         'The sorted list [2,5,8,12,16,23,38,42,50].\n16 is the middle element; 23 is sixth.\n'+table+
         'Linear uses fewer probes for target 2; binary uses fewer for the other tested targets. These are inspected items, not timings or all primitive comparisons.', 'supported'),
        ('timing-bad', TIMING, 'Linear index 3 (0.00s), Binary index 3 (0.00s)\n',
         'Both returned index 3. Binary uses 3 comparisons. Both complete in microseconds, too fast for perf_counter to show a difference.', 'unsupported'),
        ('timing-good', TIMING, 'Linear index 3 (0.00s), Binary index 3 (0.00s)\n',
         'Both returned index 3. The displayed 0.00s times do not identify a winner. No comparison counters were printed. Binary search requires sorted input and has O(log n) worst-case time; linear search has O(n).', 'supported'),
        ('duplicates-bad', SEARCH, SEARCH_STDOUT,
         'Does not handle duplicate values (returns any match).', 'unsupported'),
        ('duplicates-good', SEARCH, SEARCH_STDOUT,
         'Both algorithms accept duplicates. This left-to-right linear scan returns the first matching index; binary search can return any matching index and does not guarantee the first or last occurrence. Duplicate inputs were not tested here.', 'supported'),
        ('csv-bad', 'import csv, io\nrows = csv.DictReader(io.StringIO("value\\n2\\n6\\n"))\nvalues = [int(row["value"]) for row in rows]\nprint("mean", sum(values)/len(values))\n',
         'mean 4.0\n', 'The synthetic CSV values are 2 and 6. The execution printed mean 8.0.', 'unsupported'),
        ('csv-good', 'import csv, io\nrows = csv.DictReader(io.StringIO("value\\n2\\n6\\n"))\nvalues = [int(row["value"]) for row in rows]\nprint("mean", sum(values)/len(values))\n',
         'mean 4.0\n', 'The synthetic CSV values are 2 and 6. The execution printed mean 4.0. This two-row demonstration does not establish properties of a larger dataset.', 'supported'),
    ]
    return [{'id': name, 'fixture_expected': expected, 'human_label': None,
             'request': review_payload(answer, 'Explain the supplied synthetic experiment and its limitations.',
                 [{'tool': 'code_execute', 'executed_program': program,
                   'data': {'status': 'succeeded', 'exit_code': 0, 'stdout': stdout,
                            'stderr': '', 'stdout_truncated': False, 'stderr_truncated': False,
                            'artifacts': []}}])}
            for name, program, stdout, answer, expected in examples]


def production_client(model=None):
    from backend.ai.llm import LLM
    client = LLM().for_task('answer')
    if model:
        client.model_name = model
    client = client.for_summary().for_verification().with_output_budget(1024, exact=True)
    client.read_timeout = min(client.read_timeout, 30)
    return client


def prediction(verdict):
    return 'supported' if not Review.model_validate(verdict).issues else 'unsupported'


def scores(packet, label_key='fixture_expected'):
    rows = [row for row in packet['records'] if row.get(label_key) in LABELS]
    result = {'labelled': len(rows)}
    for field in ('model_verdict', 'effective_verdict'):
        predicted = [prediction(row[field]) if row.get(field) is not None else None for row in rows]
        bad = sum(row[label_key] == 'unsupported' for row in rows)
        result[field] = {
            'unknown': predicted.count(None),
            'agreement': sum(value == row[label_key] for value, row in zip(predicted, rows))/len(rows) if rows else None,
            'false_acceptances': sum(value == 'supported' and row[label_key] == 'unsupported' for value, row in zip(predicted, rows)),
            'unsupported_cases': bad,
        }
    return result


def fixture_warnings(packet):
    """Keep historical packets intact, but disclose the flawed v1 good example."""
    flawed = any(row.get('id') == 'duplicates-good' and
                 'neither guarantees the first or last occurrence' in
                 row.get('request', {}).get('draft_answer', '')
                 for row in packet['records'])
    return (['The duplicates-good reference is flawed: this linear scan guarantees the first match. Recorded fixture agreement is not a valid correctness score; review the original claims independently. New collections use corrected version 2 fixtures.']
            if flawed else [])


def _save(path, packet):
    # Atomic checkpoints belong to this collection; initial creation is exclusive.
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(packet, indent=2), encoding='utf-8')
    temporary.replace(path)


def collect(path, client_factory=production_client, model=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    packet = {'version': 2, 'created_at': datetime.now(timezone.utc).isoformat(),
              'evidence_origin': 'assistant-authored synthetic program/output pairs; not live code executions',
              'note': 'Fixture agreement is not human calibration or general teaching accuracy.',
              'system_prompt': REVIEW_SYSTEM, 'records': cases()}
    # Refuse overwrite before constructing a client or making any request.
    with path.open('x', encoding='utf-8') as handle:
        json.dump(packet, handle, indent=2)
    try:
        client = client_factory(model)
    except Exception:
        packet['setup_error'] = 'client_configuration_failed'
        _save(path, packet)
        return packet
    packet['model'] = client.model_name
    packet['reasoning_effort'] = client.reasoning_effort
    for row in packet['records']:
        start = time.monotonic()
        try:
            raw = client.generate_json(json.dumps(row['request']), max_retries=1, system_prompt=REVIEW_SYSTEM)
            verdict = Review.model_validate(raw)
            row['model_verdict'] = verdict.model_dump()
            forced = {finding['category']: False for finding in row['request']['deterministic_findings']}
            row['effective_verdict'] = verdict.model_copy(update=forced).model_dump()
        except Exception:
            # Never persist arbitrary provider errors, rejected JSON, URLs or keys.
            row['error'] = 'review_unavailable'
        row['latency_seconds'] = round(time.monotonic()-start, 3)
        _save(path, packet)
    return packet


def label_case(path, case_id, label):
    if label not in LABELS:
        raise ValueError('Choose supported or unsupported.')
    path = Path(path)
    packet = json.loads(path.read_text(encoding='utf-8'))
    matches = [row for row in packet['records'] if row['id'] == case_id]
    if len(matches) != 1:
        raise ValueError('Unknown case ID.')
    matches[0]['human_label'] = label
    matches[0]['human_reviewed_at'] = datetime.now(timezone.utc).isoformat()
    _save(path, packet)
    return packet


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--collect-live', action='store_true', help='Spend up to eight configured-provider requests.')
    actions.add_argument('--review-case', metavar='ID')
    parser.add_argument('--label', choices=LABELS)
    parser.add_argument('--model', help='Optional exact model ID; otherwise use the production reviewer configuration.')
    parser.add_argument('--packet', default=DEFAULT_PACKET)
    args = parser.parse_args(argv)
    if args.label and not args.review_case or args.review_case and not args.label:
        parser.error('--review-case and --label must be used together')
    try:
        packet = (collect(args.packet, model=args.model) if args.collect_live else
                  label_case(args.packet, args.review_case, args.label) if args.review_case else
                  json.loads(Path(args.packet).read_text(encoding='utf-8')))
    except (OSError, ValueError, KeyError):
        parser.exit(1, 'Cannot use this packet. Collection never overwrites an existing file; choose a new --packet path.\n')
    warnings = fixture_warnings(packet)
    print(json.dumps({'fixture_comparison': scores(packet), 'human_comparison': scores(packet, 'human_label'),
                      'fixture_reference_status': 'known_flawed' if warnings else 'assistant_authored_not_human_calibrated',
                      'fixture_warnings': warnings,
                      'setup_error': packet.get('setup_error'),
                      'note': 'Eight synthetic cases do not establish general accuracy. Inspect evidence independently before labelling.'}, indent=2))
    return 1 if packet.get('setup_error') or any(row.get('error') for row in packet['records']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
