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
