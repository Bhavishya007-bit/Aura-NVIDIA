"""Bounded source-scoped expansion after a checked long overview falls short."""
import json
import logging
import math
import time
from pathlib import Path

from backend.ai.response_request import response_request, length_check, length_distance
from backend.ai.summary_answer import (
    SummaryDraft, SummaryDraftError, summary_contract, checked_points, source_section,
)

log = logging.getLogger(__name__)
MAX_SECTIONS = 8
MAX_REPAIRS = 2
EXPANSION_SECONDS = 180


def summary_plan(sources, target):
    """Keep every representation of a slide/page together; preserve source IDs."""
    groups = {}
    for number, source in enumerate(sources, 1):
        location = (source.get('source_id'), source.get('page'), source.get('slide'),
                    source.get('timestamp_start'))
        if all(value is None for value in location[1:]):
            location = ('chunk', number)
        groups.setdefault(location, []).append(number)
    count = min(MAX_SECTIONS, math.ceil(target / 600), len(groups))
    if count < 2:
        return []
    locations = list(groups.values())
    size, extra = divmod(len(locations), count)
    words, remainder = divmod(target, count)
    plan, offset = [], 0
    for index in range(count):
        end = offset + size + (index < extra)
        plan.append({'index': index + 1, 'count': count, 'target_words': words + (index < remainder),
                     'source_ids': [n for location in locations[offset:end] for n in location]})
        offset = end
    return plan


def expand_summary(rag, client, sources, question, request, base_payload, schema_errors):
    """At most one initial call per section plus two repairs shared across sections."""
    plan = summary_plan(sources, request['target_words'])
    if not plan:
        return None
    started = time.monotonic()
    states = [{'plan': part, 'points': [], 'attempts': 0, 'last_draft': None, 'feedback': None}
              for part in plan]
    writing_calls = 0
    verification_unavailable = False
    system = (Path(__file__).with_name('prompts') / 'v1' / 'summary_answer.txt').read_text(encoding='utf-8')

    def part_request(state):
        req = response_request(f"in {state['plan']['target_words']} words")
        req.update(layout='prose', long_form=True, detailed=True)
        return req

    def write(state):
        nonlocal writing_calls, verification_unavailable
        req = part_request(state)
        part = state['plan']
        allowed = set(part['source_ids'])
        payload = {key: value for key, value in base_payload.items() if key not in
                   {'passages', 'previous_draft', 'feedback', 'draft_contract', 'supported_parts', 'missing_parts'}}
        payload.update(passages=[{'id': n, 'text': sources[n - 1]['content'][:6000]} for n in part['source_ids']],
                       supported_parts=[], missing_parts=[], response_request=req,
                       draft_contract=summary_contract(req, len(sources)), section_request=part,
                       overall_user_request=question,
                       question='Explain only this portion of the selected presentation. Honor the overall user language and style.')
        payload['draft_contract']['output_schema']['$defs']['SummarySentence']['properties']['citation_ids']['items']['enum'] = part['source_ids']
        if state['feedback'] is not None:
            payload.update(previous_draft=state['last_draft'], feedback=state['feedback'])
        writer = client.with_output_budget(req['token_budget'], exact=True) if hasattr(client, 'with_output_budget') else client
        writing_calls += 1
        state['attempts'] += 1
        draft = None
        try:
            draft = writer.generate_json(json.dumps(payload), max_retries=1,
                system_prompt=system + '\nWrite ONLY the assigned section, not the entire overview. '
                'Its target is section_request.target_words. Develop the supported ideas across '
                'its supplied passages. Do not repeat an overall introduction or conclusions. '
                'Use complete self-contained sentences, preserve scientific abbreviations, '
                'and keep every qualification on model-interpreted image content.')
            parsed = SummaryDraft.model_validate(draft)
            points = parsed.points(len(sources), req)
            if any(n not in allowed for point in points for n in point['citation_ids']):
                raise SummaryDraftError('citation_outside_section')
            text = parsed.render(len(sources), req)
            validation = rag._validate_answer(text, sources, question, structured_points=points)
            verification_unavailable = validation.get('stage') == 'verification_unavailable'
            approved = checked_points(sources, validation, question, req)
            check = length_check('', req)
            if approved:
                approved_text = SummaryDraft.model_validate({'sentences': approved}).render(len(sources), req)
                check = length_check(approved_text, req)
                old_text = (SummaryDraft.model_validate({'sentences': state['points']}).render(len(sources), req)
                            if state['points'] else '')
                if not state['points'] or length_distance(check) < length_distance(length_check(old_text, req)):
                    state['points'] = approved
            state['feedback'] = {'length_validation': check,
                'failed_points': [item for item in validation.get('grounding_validation', {}).get('results', [])
                                  if item.get('supported') is not True],
                'instruction': 'Repair unsupported points and meet this section word target using only its passages. Keep complete supported sentences; do not return an empty list.'}
            log.info('summary_section index=%s attempt=%s actual_words=%s target_words=%s stage=%s valid=%s',
                     part['index'], state['attempts'], check['actual_words'], part['target_words'],
                     validation.get('stage'), validation.get('valid') is True)
        except Exception as error:
            code = getattr(error, 'failure_code', 'schema_or_generation_failure')
            state['feedback'] = {'failure_code': code, 'schema_errors': schema_errors(error),
                                 'instruction': 'Repair the draft using draft_contract. Use a nonempty sentences list with complete supported points and only allowed source IDs.'}
            log.warning('summary_section index=%s attempt=%s failure_code=%s error_type=%s',
                        part['index'], state['attempts'], code, type(error).__name__)
        state['last_draft'] = draft

    def combined():
        points, seen = [], set()
        for state in states:
            for point in state['points']:
                key = ' '.join(point['text'].casefold().split())
                if key not in seen:
                    seen.add(key)
                    points.append(point)
        return points[:request['max_sentences']]

    for state in states:
        if time.monotonic() - started >= EXPANSION_SECONDS or verification_unavailable:
            break
        write(state)
    for _ in range(MAX_REPAIRS):
        points = combined()
        text = SummaryDraft.model_validate({'sentences': points}).render(len(sources), request) if points else ''
        if length_check(text, request)['valid'] or verification_unavailable or time.monotonic() - started >= EXPANSION_SECONDS:
            break
        candidates = [s for s in states if s['attempts'] == 1]
        if not candidates:
            break
        def deficit(state):
            req = part_request(state)
            text = SummaryDraft.model_validate({'sentences': state['points']}).render(len(sources), req) if state['points'] else ''
            return length_distance(length_check(text, req))
        write(max(candidates, key=deficit))
    points = combined()
    if not points:
        return None
    text = SummaryDraft.model_validate({'sentences': points}).render(len(sources), request)
    check = length_check(text, request)
    complete = check['valid'] and all(s['points'] for s in states)
    return source_section(text), {'valid': True, 'stage': 'summary_section_expansion',
        'response_mode': 'generated' if complete else 'checked_points', 'length_validation': check,
        'writing_calls': writing_calls, 'section_count': len(plan),
        'grounding_validation': {'valid': True, 'results': [
            {'claim': p['text'], 'citations': p['citation_ids'], 'supported': True} for p in points]}}
