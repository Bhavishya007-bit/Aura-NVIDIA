"""Human-only, resumable coverage review. No model calls or automatic labels."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from backend.evaluation_status import calibration_summary

DEFAULT_PACKET = 'evaluation/results/judge_calibration.json'
CHOICES = {'f': 'fully_covered', 'p': 'partially_covered', 'n': 'not_covered'}


def _load(path):
    original = path.read_bytes()
    packet = json.loads(original.decode('utf-8-sig'))
    fixture = json.loads(Path(__file__).with_name('calibration_cases.json').read_text(encoding='utf-8'))
    expected = {row['id']: row['question'] for row in fixture['cases']}
    rows = packet.get('records') if isinstance(packet, dict) else None
    valid = (isinstance(rows, list) and len(rows) == 30 and
             all(isinstance(row, dict) and isinstance(row.get('id'), str) for row in rows) and
             {row['id'] for row in rows} == set(expected))
    if not valid:
        raise ValueError('Review needs all 30 unique cases. Keep this packet; finish collection or select the complete file.')
    if (packet.get('mode') != 'live_synthetic' or not isinstance(packet.get('model'), str) or not packet['model'] or
        packet.get('passages') != fixture['passages'] or
        any(row.get('question') != expected[row['id']] for row in rows)):
        raise ValueError('The packet does not match the current synthetic calibration fixture. Keep it and use the matching code version.')
    return packet, original


def _save(path, packet, expected_bytes):
    """Checkpoint one explicit judgment, preserving the last good file on error."""
    serialized = json.dumps(packet, ensure_ascii=False, indent=2).encode('utf-8')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.calibration-', suffix='.tmp', delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
        if path.read_bytes() != expected_bytes:
            raise ValueError('The packet changed during review. Your other changes were preserved; restart to load them.')
        os.replace(temporary, path)
        return serialized
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _display(value):
    # Evidence is data, including any terminal escape characters it might contain.
    return ''.join(char for char in value if char.isprintable() or char in '\n\t')


def review(path, ask=None, write=print):
    path = Path(path)
    packet, current_bytes = _load(path)
    ask = input if ask is None else ask
    write('Read each question against the passages and enter your own judgment. Model decisions and reference labels stay hidden.')
    write('f = every requested part is covered; p = only part is covered; n = no requested answer is covered; q = save progress and quit.')
    for row in packet['records']:
        if row.get('reviewed_by') == 'human' and row.get('human_label') in CHOICES.values():
            continue
        write('\nQuestion '+row['id']+': '+_display(row['question']))
        write('Supplied passages:')
        for passage in packet['passages']:
            write('['+str(passage['id'])+'] '+_display(passage['text']))
        while True:
            try:
                choice = ask('Your judgment [f/p/n/q]: ').strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = 'q'
            if choice == 'q':
                summary = calibration_summary(packet)
                write('Saved progress: '+str(summary['reviewed'])+'/30 human judgments. Run this command again to resume.')
                return summary
            if choice not in CHOICES:
                write('Enter f, p, n or q. No label was saved for this question.')
                continue
            row.update(human_label=CHOICES[choice], reviewed_by='human',
                       reviewed_at=datetime.now(timezone.utc).isoformat())
            current_bytes = _save(path, packet, current_bytes)
            write('Saved your judgment.')
            break
    summary = calibration_summary(packet)
    write('All 30 human judgments are saved. Agreement below compares your labels with the collected model outputs; this small synthetic set does not establish general teaching accuracy.')
    write(json.dumps(summary, indent=2))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet', default=DEFAULT_PACKET)
    args = parser.parse_args(argv)
    try:
        review(args.packet)
    except (OSError, ValueError) as error:
        # Validation messages are fixed; never print an arbitrary path/error body.
        message = str(error) if type(error) is ValueError else 'Cannot read or save the packet. Existing saved progress was preserved.'
        parser.exit(1, message+'\n')


if __name__ == '__main__':
    main()
