"""Conservative internal-consistency checks, never execution or universal NLP proof.

Checks explicit small numeric lists and English position labels in an answer.
The model reviewer still owns comparison with the real execution evidence.
"""
from decimal import Decimal
import re

NUMBER = r'[+-]?\d{1,18}(?:\.\d{1,10})?'
LIST = re.compile(r'\[\s*(' + NUMBER + r'(?:\s*,\s*' + NUMBER + r')+)\s*\]')
DATA = re.compile(r'\b(?:list|array|values)\s*(?:(?:is|was|are|were|=|:)\s*)?$')
TARGETS = re.compile(r'\btargets?(?:\s+(?:list|array|values))?\s*(?:(?:is|was|are|were|=|:)\s*)?$')
LABEL = r'(first|last|middle|absent|not present)(?:\s+(?:element|value))?'
DIRECT = re.compile(r'(?<![\w.])(' + NUMBER + r')\s+(?:is|was)\s+(?:the\s+)?(first|last|middle)\s+(?:element|value)\b', re.I)
PAREN = re.compile(r'(?<![\w.])(' + NUMBER + r')\s*\(\s*' + LABEL + r'\s*\)', re.I)
REVERSE = re.compile(r'\b(first|last|middle)\s+(?:element|value)\s+(?:is|was|=|:)\s*(' + NUMBER + r')(?!\w|\.\d)', re.I)


def _text(answer):
    text = re.sub(r'(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$', '', answer)
    text = re.sub(r'(?m)^\s*>.*$', '', text)
    return text.replace('`', '').replace('**', '').replace('__', '')


def _lists(text):
    for match in LIST.finditer(text):
        values = [Decimal(item.strip()) for item in match.group(1).split(',')]
        if len(values) <= 64:
            yield match, values


def _counterexample(text):
    """Find a reported table row where linear checks fewer items than binary."""
    columns = None
    tables, example = 0, None
    for line in text.splitlines():
        if '|' not in line:
            columns = None
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        linear = [i for i, name in enumerate(cells) if re.search(r'linear.*(?:comparisons|checks|probes|items)', name, re.I)]
        binary = [i for i, name in enumerate(cells) if re.search(r'binary.*(?:comparisons|checks|probes|items)', name, re.I)]
        if len(linear) == len(binary) == 1:
            tables += 1
            if tables > 1:
                return None  # Do not guess which table a later conclusion refers to.
            columns = (linear[0], binary[0])
            continue
        if columns is None:
            continue
        if max(columns) >= len(cells):
            continue
        a, b = (cells[i] for i in columns)
        if re.fullmatch(r'\d{1,9}', a) and re.fullmatch(r'\d{1,9}', b) and int(a) < int(b):
            example = {'linear_count': int(a), 'binary_count': int(b)}
    return example


def explanation_findings(answer):
    """Return only definite contradictions within recognized answer patterns.

    Unknown syntax/languages, dynamic lists and mathematical expressions are
    left to the model review. Values in the answer are not asserted to be real
    runtime data. No generated Python, regex from users, eval or imports run.
    """
    text = _text(answer)
    arrays = []
    numeric_lists = list(_lists(text))
    for match, values in numeric_lists:
        prefix = text[max(0, match.start()-90):match.start()]
        if DATA.search(prefix.lower()) and not TARGETS.search(prefix.lower()):
            arrays.append((match.start(), values))
    findings = []
    # A narrow self-contradiction, not a claim about every implementation.
    # Whole-clause matching avoids quoted mistakes and first/last guarantees.
    for clause in re.split(r'[.!?]\s+|\n', text):
        clause = clause.strip().lstrip('-* ').rstrip('.')
        if re.fullmatch(r"(?:(?:binary search|linear search|the algorithm|it)\s+)?(?:does not|doesn't|cannot|can't)\s+handle\s+duplicate(?:s| values)?\s*\(\s*(?:it\s+)?returns?\s+any\s+match\s*\)", clause, re.I):
            findings.append({'category': 'assumptions', 'rule': 'duplicate_match_semantics',
                'instruction': 'Returning any matching index handles duplicate values. State that it does not guarantee the first or last occurrence; distinguish this from duplicates not being tested.'})

    def position(number, label, offset, end):
        before = text[max(0, offset-50):offset]
        after = text[end:end+45]
        if (re.search(r'(?:avoid|never|do not|don.t|incorrectly|wrongly)\s+(?:\w+\s+){0,4}[\'"“]?$', before, re.I)
            or re.match(r'\s*[\'"”]?\s+(?:is|was)\s+(?:incorrect|wrong|false)\b', after, re.I)):
            return
        # Several different arrays make an implicit reference ambiguous.
        if len({tuple(values) for _, values in arrays}) != 1:
            return
        candidates = [values for start, values in arrays if start < offset]
        if not candidates:
            return
        values = candidates[-1]
        target, label = Decimal(number), label.lower()
        if label == 'middle' and (len(values) % 2 == 0 or values != sorted(values)):
            return  # Avoid ambiguity with a median or either central item.
        expected = {'first': [values[0]], 'last': [values[-1]],
                    'middle': [values[(len(values)-1)//2], values[len(values)//2]]}
        wrong = target not in expected[label] if label in expected else target in values
        if wrong:
            findings.append({'category': 'assumptions', 'rule': 'numeric_list_position',
                'claimed_value': number, 'claimed_position': label, 'list_length': len(values),
                'matching_indices': [i for i, value in enumerate(values) if value == target],
                'expected_values': list(dict.fromkeys(str(v) for v in expected.get(label, [])))})

    for pattern in (DIRECT, PAREN, REVERSE):
        for match in pattern.finditer(text):
            number, label = (match.group(2), match.group(1)) if pattern is REVERSE else match.groups()
            position(number, label, match.start(), match.end())
    for match, targets in numeric_lists:
        prefix = text[max(0, match.start()-70):match.start()]
        labels = re.match(r'\s*\(([^)\n]{1,160})\)', text[match.end():])
        if not TARGETS.search(prefix.lower()) or not labels:
            continue
        parts = [part.strip().lower() for part in labels.group(1).split(',')]
        if len(parts) != len(targets):
            continue
        for number, part in zip(targets, parts):
            label = re.fullmatch(LABEL, part, re.I)
            if label:
                position(str(number), label.group(1), match.start(), match.end()+labels.end())

    example = _counterexample(text)
    if example:
        for sentence in re.split(r'[.!?]\s+|\n', text):
            observed = re.search(r'\b(?:results|table|experiment)\s+(?:show|shows|confirm|confirms|prove|proves|demonstrate|demonstrates)\b', sentence, re.I)
            general = re.search(r'\bbinary search\s+(?:always\s+)?(?:uses|makes|requires|needs)\s+(?:significantly\s+|consistently\s+)?fewer\s+(?:comparisons|checks|probes)\s+than\s+linear search\b', sentence, re.I)
            qualified = re.search(r'\b(?:for (?:the )?targets?\b|except|although|whereas|but|worst.case|absent|missing|sometimes|usually|typically|often)\b', sentence, re.I)
            if observed and general and not qualified:
                findings.append({'category': 'counts_and_timing', 'rule': 'comparison_counterexample',
                    **example, 'instruction': 'Qualify the conclusion: the table includes a case where linear uses fewer checks. One list size does not measure scaling.'})
                break
    # Bound repair context without copying raw answer sentences or instructions.
    unique = {str(finding): finding for finding in findings}
    return list(unique.values())[:8]


def execution_findings(answer, observation):
    """Guard recognized timing-only search reports against invented count data.

    This does not infer timer resolution or run the program. Unknown report
    formats remain outside the guard; the model review still checks them.
    """
    data = observation.get('data', {})
    if not isinstance(data, dict):
        return []
    stdout = data.get('stdout', '')
    if not isinstance(stdout, str):
        return []
    times = list(re.finditer(r'\b(\d{1,18}(?:\.\d{1,18})?(?:[eE][+-]?\d{1,3})?)\s*(s|seconds?|ms|us|µs|ns)\b', stdout))
    index_report = re.search(r'\b(?:linear|binary)[ _]+index\b', stdout, re.I)
    time_header = re.search(r'\b(?:linear|binary)[ _]+time\b', stdout, re.I)
    count_label = re.search(r'\b(?:linear|binary)[ _]+(?:comparisons?|comps?|probes?|checks|inspected_items)\b', stdout, re.I)
    count_value = re.search(r'\b(?:comparisons?|comps?|probes?|checks|inspected(?:_items)?)\s*[:=]?\s*\d+|\b\d+\s+(?:comparisons?|comps?|probes?|checks)\b|\b(?:linear|binary)\s*[:=]\s*\d+\s*(?:comps?|comparisons?|probes?|checks)\b', stdout, re.I)
    trace_label = re.search(r'\b(?:(?:linear|binary)[_ ])?(?:trace|visited)\b|\b(?:mid|midpoint)\s*[:=]', stdout, re.I)
    if not index_report or not (times or time_header):
        return []
    text = _text(answer)
    findings = []
    number = r'(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)'
    numeric_count = re.search(r'\b'+number+r'\s+(?:comparisons?|comps?|probes?|checks)\b', text, re.I)
    # Count tables are quantitative assertions too, not a workaround for prose.
    count_table = False
    lines = text.splitlines()
    for index, line in enumerate(lines):
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        columns = [i for i, cell in enumerate(cells) if re.search(r'comparisons?|probes?|checks', cell, re.I)] if '|' in line else []
        for row in lines[index+1:index+6] if columns else []:
            if '|' not in row:
                break
            values = [cell.strip() for cell in row.strip().strip('|').split('|')]
            if any(i < len(values) and re.fullmatch(r'[~≈]?\s*\d+(?:\.\d+)?', values[i]) for i in columns):
                count_table = True
    if (numeric_count or count_table) and not (count_label or count_value or trace_label):
        findings.append({'category':'counts_and_timing','rule':'unrecorded_comparison_counts',
            'instruction':'Visible execution evidence reports indices and times, not comparison counters. Remove numerical count/average estimates and invented count tables from this timing-only experiment. Explain qualitative complexity instead; do not relabel unrecorded numbers as measured or confirmed.'})
    zeros_only = bool(times) and all(Decimal(match.group(1)) == 0 for match in times)
    resolution_reported = re.search(r'\bresolution\b', stdout, re.I)
    clock_blame = re.search(r'\btoo\s+(?:fast|small)\s+for\s+[^\n]{0,60}\b(?:perf_counter|timer|clock)\b|\b(?:perf_counter|timer|clock)\b[^\n]{0,50}\b(?:lacks?|insufficient|too low|too coarse)\b[^\n]{0,25}\b(?:precision|resolution)\b', text, re.I)
    if zeros_only and clock_blame and not resolution_reported:
        findings.append({'category':'counts_and_timing','rule':'timer_resolution_inference',
            'instruction':'Displayed 0.00s values do not establish timer resolution or show that perf_counter lacks precision. Explain that the displayed timings are insufficient to identify a winner; distinguish formatting/rounding and benchmark noise from clock resolution.'})
    unit_claim = re.search(r'\b(?:complete|completes|completed|finish|finished|execute|executed|take|takes|took|run|runs)\s+(?:in\s+)?(?:a\s+few\s+)?(?:microseconds|nanoseconds)\b', text, re.I)
    if zeros_only and unit_claim and not re.search(r'\b(?:may|might|could|typically)\s+[^.\n]{0,25}'+re.escape(unit_claim.group(0)), text, re.I):
        findings.append({'category':'counts_and_timing','rule':'unobserved_time_unit',
            'instruction':'Only zero-valued displayed timings are visible. Do not claim observed microsecond/nanosecond durations from them; no such precise durations were captured in the review evidence.'})
    return findings
