"""Bounded source-scoped expansion after a checked long overview falls short."""
import json
import logging
import math
import time
from pathlib import Path

from backend.ai.response_request import response_request, length_check, length_distance
from backend.ai.llm import LLMConnectionError
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


def expand_summary(rag, client, sources, question, request, base_payload, schema_errors, *, seed_check=None):
    """At most one initial call per section plus two repairs shared across sections."""
    plan = summary_plan(sources, request['target_words'])
    if not plan:
        return None
    started = time.monotonic()
    states = [{'plan': part, 'points': [], 'seed_words': 0, 'attempts': 0, 'last_draft': None, 'feedback': None}
              for part in plan]
    # Only points carrying an existing positive support result can seed expansion.
    # Preserve their original order so pronouns keep their checked antecedents.
    seed_points = []
    for item in (seed_check or {}).get('grounding_validation', {}).get('results', []):
        if item.get('supported') is not True:
            continue
        try:
            point = SummaryDraft.model_validate({'sentences': [{'text': item.get('claim'),
                'citation_ids': item.get('citations') or [item.get('citation')]}]}).points(len(sources))[0]
        except (ValueError, TypeError):
            continue
        seed_points.append(point)
        state = max(states, key=lambda s: len(set(point['citation_ids']) & set(s['plan']['source_ids'])))
        state['seed_words'] += length_check(SummaryDraft.model_validate({'sentences': [point]}).render(len(sources)), request)['actual_words']
    writing_calls = 0
    verification_unavailable = False
    connection_unavailable = False
    system = (Path(__file__).with_name('prompts') / 'v1' / 'summary_answer.txt').read_text(encoding='utf-8')

    def part_request(state):
        req = response_request(f"in {state['plan']['target_words']} words")
        req.update(layout='prose', long_form=True, detailed=True)
        return req

    def render_points(points, req):
        return (SummaryDraft.model_validate({'sentences': points}).render(len(sources),
                {**req, 'max_sentences': request['max_sentences']}) if points else '')

    def combined():
        points, seen = [], set()
        for group in [seed_points] + [state['points'] for state in states]:
            for point in group:
                key = ' '.join(point['text'].casefold().split())
                if key not in seen:
                    seen.add(key)
                    points.append(point)
        return points[:request['max_sentences']]

    def overall_check():
        return length_check(render_points(combined(), request), request)

    def deficit(state):
        return max(0, state['plan']['target_words'] - length_check(
            render_points(state['points'], part_request(state)), part_request(state))['actual_words'] - state['seed_words'])

    def write(state):
        nonlocal writing_calls, verification_unavailable, connection_unavailable
        part = state['plan']
        remaining = max(1, request['target_words'] - overall_check()['actual_words'])
        additional_target = min(remaining, max(80, deficit(state)))
        req = response_request(f'in {additional_target} words')
        req.update(layout='prose', long_form=True, detailed=True)
        allowed = set(part['source_ids'])
        payload = {key: value for key, value in base_payload.items() if key not in
                   {'passages', 'previous_draft', 'feedback', 'draft_contract', 'supported_parts', 'missing_parts'}}
        payload.update(passages=[{'id': n, 'text': sources[n - 1]['content'][:6000]} for n in part['source_ids']],
                       supported_parts=[], missing_parts=[], response_request=req,
                       draft_contract=summary_contract(req, len(sources)),
                       section_request={**part, 'target_words': additional_target,
                                        'section_total_target_words': part['target_words']},
                       already_explained=combined(),
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
                system_prompt=system + '\nWrite ONLY additional teaching points for the assigned section. '
                'The word target is for NEW text only: section_request.target_words. '
                'The already_explained points are already in the answer; develop other supported '
                'details, terms, comparisons or mechanisms from this section. Do not rewrite or '
                'repeat those points or fill the count with paraphrases of the same facts. '
                'Already explained points are context, not new source evidence. '
                'Use complete self-contained sentences, preserve scientific abbreviations, '
                'and keep every qualification on model-interpreted image content.')
            parsed = SummaryDraft.model_validate(draft)
            points = parsed.points(len(sources), req)
            if any(n not in allowed for point in points for n in point['citation_ids']):
                raise SummaryDraftError('citation_outside_section')
            text = parsed.render(len(sources), req)
            intent = {'scope': 'selected_material_section',
                      'section_question': 'Explain teaching points from this assigned portion of the selected presentation.',
                      'passages': [{'id': n, 'text': sources[n - 1]['content'][:500]} for n in part['source_ids']]}
            validation = rag._validate_answer(text, sources, question, structured_points=points, intent_context=intent)
            verification_unavailable = validation.get('stage') == 'verification_unavailable'
            approved = checked_points(sources, validation, question, req)
            before = overall_check()['actual_words']
            seen = {' '.join(p['text'].casefold().split()) for p in combined()}
            for point in approved:
                key = ' '.join(point['text'].casefold().split())
                if key in seen or len(combined()) >= request['max_sentences']:
                    continue
                old_distance = length_distance(overall_check())
                state['points'].append(point)
                if length_distance(overall_check()) < old_distance:
                    seen.add(key)
                else:
                    state['points'].pop()
            check = length_check(render_points(state['points'], part_request(state)), part_request(state))
            check['actual_words'] += state['seed_words']
            check['valid'] = max(1, int(part['target_words'] * .9)) <= check['actual_words'] <= int(part['target_words'] * 1.1)
            state['feedback'] = {'length_validation': check, 'stage': validation.get('stage'),
                'question_validation': validation.get('question_validation'),
                'failed_points': [item for item in validation.get('grounding_validation', {}).get('results', [])
                                  if item.get('supported') is not True],
                'instruction': 'Add only missing supported teaching points using this section passages. Existing checked points are retained. Use the updated additional word target and do not return an empty list.'}
            log.info('summary_section index=%s attempt=%s actual_words=%s target_words=%s stage=%s valid=%s '
                     'generated_words=%s new_checked_words=%s additional_target_words=%s intent_scope=selected_material_section',
                     part['index'], state['attempts'], check['actual_words'], part['target_words'],
                     validation.get('stage'), validation.get('valid') is True,
                     length_check(text, req)['actual_words'], overall_check()['actual_words'] - before, additional_target)
        except Exception as error:
            if isinstance(error, LLMConnectionError):
                connection_unavailable = True
            code = getattr(error, 'failure_code', 'schema_or_generation_failure')
            state['feedback'] = {'failure_code': code, 'schema_errors': schema_errors(error),
                                 'instruction': 'Repair the draft using draft_contract. Use a nonempty sentences list with complete supported points and only allowed source IDs.'}
            log.warning('summary_section index=%s attempt=%s failure_code=%s error_type=%s',
                        part['index'], state['attempts'], code, type(error).__name__)
        state['last_draft'] = draft

    for state in states:
        if time.monotonic() - started >= EXPANSION_SECONDS or verification_unavailable or connection_unavailable or overall_check()['valid']:
            break
        if not deficit(state):
            continue
        write(state)
    for _ in range(MAX_REPAIRS):
        points = combined()
        text = SummaryDraft.model_validate({'sentences': points}).render(len(sources), request) if points else ''
        if length_check(text, request)['valid'] or verification_unavailable or connection_unavailable or time.monotonic() - started >= EXPANSION_SECONDS:
            break
        candidates = [s for s in states if s['attempts'] == 1 and deficit(s)]
        if not candidates:
            break
        write(max(candidates, key=deficit))
    points = combined()
    if not points:
        return None
    text = SummaryDraft.model_validate({'sentences': points}).render(len(sources), request)
    check = length_check(text, request)
    complete = check['valid'] and all(s['points'] or s['seed_words'] for s in states)
    return source_section(text), {'valid': True, 'stage': 'summary_section_expansion',
        'response_mode': 'generated' if complete else 'checked_points', 'length_validation': check,
        'writing_calls': writing_calls, 'section_count': len(plan),
        'grounding_validation': {'valid': True, 'results': [
            {'claim': p['text'], 'citations': p['citation_ids'], 'supported': True} for p in points]}}
