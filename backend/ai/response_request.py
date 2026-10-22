"""Interpret response constraints without confusing them with a new subject."""
import math
import re

MAX_RESPONSE_WORDS = 5000
FORMAT_MARKER = '\nAnswer format requested now: '
WORD_PATTERN = re.compile(r'\b(\d[\d,]*)(?:\s*[-–]\s*|\s+)(words?|sentences?|paragraphs?)\b', re.I)
LANGUAGES = 'english hindi tamil telugu bengali marathi french spanish german chinese mandarin japanese korean'.split()
MODIFIER_WORDS = set(('please in about around roughly approximately exactly make it this that the answer response summary '
    'explanation version write give me to of and with at least more most than a an word words use now could can you '
    'be long length expand rewrite summarize explain detailed detail deeper simpler simply simple shorter brief '
    'briefly concise beginner advanced technical terms language translate as into bullet bullets points point '
    'paragraph paragraphs form format table tabular sentence sentences go elaboration elaborate expand expanded '
    'using only examples example explain continue same keep change short longer '
    'i want need would should do tell provide produce turn instead rather output previous '
    'all details current earlier full complete comprehensive including also both').split()) | set(LANGUAGES)


def normalize_numbers(text):
    text = re.sub(r'\b(\d+(?:\.\d+)?)\s*k\s*(?=words?\b)',
                  lambda m: str(round(float(m[1]) * 1000)) + ' ', text, flags=re.I)
    numbers = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'ten': 10}
    text = re.sub(r'\b(one|two|three|four|five|ten)\s+(hundred|thousand)\s*(?=words?\b)',
                  lambda m: str(numbers[m[1].lower()] * (100 if m[2].lower() == 'hundred' else 1000)) + ' ', text, flags=re.I)
    return re.sub(r'\b(one|two|three|four|five|ten)(?=\s+(?:words?|sentences?|paragraphs?)\b)',
                  lambda m: str(numbers[m[1].lower()]), text, flags=re.I)


def is_format_followup(text):
    normalized = normalize_numbers(text)
    has_constraint = bool(WORD_PATTERN.search(normalized) or re.search(
        r'\b(?:paragraph|bullets?|table|tabular|go deeper|detail|detailed|simpler|simply|shorter|longer|brief|concise|translate|examples?|elaborate|continue)\b', normalized, re.I)
        or re.fullmatch(r'\s*(?:in |into |answer in |explain in )?(?:' + '|'.join(LANGUAGES) + r')[.!?]*\s*', normalized, re.I))
    if not has_constraint:
        return False
    for language in LANGUAGES:
        if re.search(r'\b' + language + r'\b', normalized, re.I) and not re.search(
            r'\b(?:in|into|to)\s+' + language + r'\b', normalized, re.I):
            # "Explain Hindi in 2000 words" names a subject; "in Hindi" is
            # a response-language modifier. Do not silently substitute topics.
            return False
    remainder = WORD_PATTERN.sub('', normalized)
    return set(re.findall(r'[a-z]+', remainder.casefold())) <= MODIFIER_WORDS


def resolve_format_followup(question, history, fallback=None):
    if not is_format_followup(question):
        return question
    modifiers = [question.strip()]
    for turn in reversed(history[-8:]):
        if turn.get('role') != 'user' or not isinstance(turn.get('content'), str):
            continue
        previous = turn['content'].strip()
        if not previous:
            continue
        if is_format_followup(previous):
            modifiers.append(previous)
        else:
            return previous + ''.join(FORMAT_MARKER + m for m in reversed(modifiers))
    return (fallback + ''.join(FORMAT_MARKER + m for m in reversed(modifiers))) if fallback else question


def word_count(text):
    text = re.sub(r'\[\d+\]|【\d+】', '', text)
    return len(re.findall(r"\b\w+(?:[’'-]\w+)*\b", text))


def response_request(question):
    target, requested, sentences, paragraphs, layout = None, None, None, None, 'prose'
    detailed = False
    for part in re.split(r'\n(?:Answer format requested now|Follow-up request):', question):
        if re.search(r'\b(?:go deeper|in detail|detailed|more detail|elaborate|expand)\b', part, re.I):
            detailed = True
        matches = list(WORD_PATTERN.finditer(normalize_numbers(part)))
        for m in matches:
            n = int(m[1].replace(',', ''))
            if not 1 <= n <= 100_000:
                continue
            unit = m[2].casefold()
            if unit.startswith('word'):
                requested, target = n, min(n, MAX_RESPONSE_WORDS)
                sentences, paragraphs = None, None
            elif unit.startswith('sentence'):
                sentences, target, requested = min(n, 160), None, None
            else:
                paragraphs = min(n, 30)
        if not matches and re.search(r'\b(?:shorter|brief|briefly|concise)\b', part, re.I):
            target, requested = None, None
            detailed = False
        if re.search(r'\b(?:bullets?|bullet points)\b', part, re.I):
            layout = 'bullets'
            paragraphs = None
        elif re.search(r'\b(?:table|tabular)\b', part, re.I):
            layout = 'table'
            paragraphs = None
        elif re.search(r'\bparagraph(?: form)?\b', part, re.I):
            layout = 'prose'
    long_form = bool((target and target >= 700) or detailed)
    return {'target_words': target, 'requested_words': requested, 'target_sentences': sentences,
            'target_paragraphs': paragraphs, 'layout': layout, 'long_form': long_form, 'detailed': detailed,
            'max_sentences': min(192, max(8, math.ceil(target / 12) + 8)) if target else (sentences or max(24 if detailed else 8, (paragraphs or 0) * 3)),
            'token_budget': min(16384, max(4096, math.ceil(((target or 0) * 2.8 + 2048) / 1024) * 1024)),
            'tolerance': 0.1}


def length_check(text, request):
    actual = word_count(text)
    target = request['target_words']
    refs = re.findall(r'(?:\[\d+\]|【\d+】)(?:[ \t]*(?:\[\d+\]|【\d+】))*', text)
    actual_sentences = len(refs) if refs else len([s for s in re.split(r'[.!?]+(?:\s|$)', text) if s.strip()])
    actual_paragraphs = len([p for p in re.split(r'\n\s*\n', text) if p.strip()])
    target_sentences, target_paragraphs = request.get('target_sentences'), request.get('target_paragraphs')
    valid = (not target or max(1, math.floor(target * .9)) <= actual <= math.ceil(target * 1.1))
    valid = valid and (not target_sentences or actual_sentences == target_sentences)
    valid = valid and (not target_paragraphs or actual_paragraphs == target_paragraphs)
    return {'valid': valid, 'actual_words': actual, 'target_words': target,
            'requested_words': request['requested_words'], 'actual_sentences': actual_sentences,
            'target_sentences': target_sentences, 'actual_paragraphs': actual_paragraphs,
            'target_paragraphs': target_paragraphs}


def length_distance(check):
    return sum(abs(check['actual_' + unit] - check['target_' + unit])
               for unit in ('words', 'sentences', 'paragraphs') if check.get('target_' + unit))
