"""Bounded, topic-led rewriting of a checked overview that falls short."""
import json
import logging
import time
from pathlib import Path

from backend.ai.response_request import response_request, length_check, length_distance
from backend.ai.llm import LLMConnectionError
from backend.ai.summary_answer import SummaryDraft, summary_contract, checked_points, source_section
from backend.ai.summary_outline import summary_plan, topic_plan

log = logging.getLogger(__name__)
MAX_REPAIRS = 2
EXPANSION_SECONDS = 180


def expand_summary(rag, client, sources, question, request, base_payload, schema_errors):
    """One outline, one complete draft per topic, and two shared replacement drafts.

    The caller retains the checked overview as a fallback. Do not prepend it to a
    rewritten lesson: it already mentions most topics and causes repeated prose.
    """
    fallback = summary_plan(sources, request['target_words'])
    if not fallback:
        log.info('summary_expansion=skipped reason=section_plan_unavailable')
        return None
    started = time.monotonic()
    if time.monotonic() - started >= EXPANSION_SECONDS:
        return None
    try:
        plan = topic_plan(client, sources, question, fallback)
    except LLMConnectionError:
        log.warning('summary_expansion=stopped reason=outline_connection_unavailable')
        return None
    states = [{'plan': part, 'points': [], 'attempts': 0, 'last_draft': None, 'feedback': None}
              for part in plan]
    writing_calls = 0
    verification_unavailable = False
    connection_unavailable = False
    system = (Path(__file__).with_name('prompts') / 'v1' / 'summary_long.txt').read_text(encoding='utf-8')

    def part_request(state):
        req = response_request(f"in {state['plan']['target_words']} words")
        req.update(layout='prose', long_form=True, detailed=True)
        return req

    def render_points(points, req):
        return (SummaryDraft.model_validate({'sentences': points}).render(len(sources),
                {**req, 'max_sentences': request['max_sentences']}) if points else '')

    def combined(exclude=None):
        points, seen = [], set()
        for state in states:
            if state is exclude:
                continue
            for point in state['points']:
                key = ' '.join(point['text'].casefold().split())
                if key not in seen:
                    seen.add(key)
                    points.append(point)
        return points[:request['max_sentences']]

    def overall_check():
        return length_check(render_points(combined(), request), request)

    def section_check(state):
        return length_check(render_points(state['points'], part_request(state)), part_request(state))

    def stopped():
        return (time.monotonic() - started >= EXPANSION_SECONDS
                or verification_unavailable or connection_unavailable)

    def write(state):
        nonlocal writing_calls, verification_unavailable, connection_unavailable
        part = state['plan']
        req = part_request(state)
        # One local citation namespace for writing, repair and verification.
        local_sources = [sources[number-1] for number in part['source_ids']]
        local_ids = list(range(1, len(local_sources)+1))
        other_points = combined(exclude=state)
        payload = {key: value for key, value in base_payload.items() if key not in
                   {'passages', 'previous_draft', 'feedback', 'draft_contract', 'supported_parts',
                    'missing_parts', 'conversation_context'}}
        payload.update(passages=[{'id': n, 'text': source['content'][:6000]} for n, source in enumerate(local_sources, 1)],
                       supported_parts=[], missing_parts=[], response_request=req,
                       draft_contract=summary_contract(req, len(local_sources)),
                       section_request={**part, 'source_ids': local_ids, 'mode': 'complete_replacement',
                                        'section_total_target_words': part['target_words']},
                       lesson_outline=[{'title': s['plan']['title'], 'focus': s['plan']['focus']} for s in states],
                       already_explained=[{'text': point['text']} for point in other_points],
                       overall_user_request=question,
                       question='Explain the assigned topic and teaching focus from the selected material. Honor the overall user language and style.')
        payload['draft_contract']['output_schema']['$defs']['SummarySentence']['properties']['citation_ids']['items']['enum'] = local_ids
        if state['feedback'] is not None:
            payload.update(previous_draft=state['last_draft'], feedback=state['feedback'])
        writer = client.with_output_budget(req['token_budget'], exact=True) if hasattr(client, 'with_output_budget') else client
        writing_calls += 1
        state['attempts'] += 1
        draft = None
        try:
            draft = writer.generate_json(json.dumps(payload), max_retries=1, system_prompt=system)
            parsed = SummaryDraft.model_validate(draft)
            points = parsed.points(len(local_sources), req)
            text = parsed.render(len(local_sources), req)
            intent = {'scope': 'selected_material_section',
                      'section_question': part['title'] + ': ' + part['focus'],
                      'already_explained': payload['already_explained'],
                      'passages': [{'id': n, 'text': source['content'][:500]} for n, source in enumerate(local_sources, 1)]}
            validation = rag._validate_answer(text, local_sources, question, structured_points=points, intent_context=intent)
            verification_unavailable = validation.get('stage') == 'verification_unavailable'
            approved = [{'text': point['text'], 'citation_ids': [part['source_ids'][n-1] for n in point['citation_ids']]}
                        for point in checked_points(local_sources, validation, question, req)]
            seen = {' '.join(p['text'].casefold().split()) for p in other_points}
            candidate = []
            for point in approved:
                key = ' '.join(point['text'].casefold().split())
                if key not in seen and len(other_points) + len(candidate) < request['max_sentences']:
                    seen.add(key)
                    candidate.append(point)
            before = section_check(state)
            check = length_check(render_points(candidate, req), req)
            # Revision replaces a section atomically; failed/worse revisions do
            # not remove its checked predecessor. Never append paraphrases.
            if candidate and (not state['points'] or length_distance(check) < length_distance(before)):
                state['points'] = candidate
            state['feedback'] = {'length_validation': check, 'stage': validation.get('stage'),
                'question_validation': validation.get('question_validation'),
                'failed_points': [item for item in validation.get('grounding_validation', {}).get('results', [])
                                  if item.get('supported') is not True],
                'instruction': 'Rewrite the ENTIRE assigned section to its word target. This replaces the previous section; nothing is appended. Develop its distinct mechanisms, relationships and supported examples. Do not recap other topics or return an empty list.'}
            log.info('summary_section index=%s attempt=%s actual_words=%s target_words=%s stage=%s valid=%s '
                     'generated_words=%s retained_words=%s mode=complete_replacement intent_scope=selected_material_section',
                     part['index'], state['attempts'], check['actual_words'], part['target_words'],
                     validation.get('stage'), validation.get('valid') is True,
                     length_check(text, req)['actual_words'], section_check(state)['actual_words'])
        except Exception as error:
            if isinstance(error, LLMConnectionError):
                connection_unavailable = True
            code = getattr(error, 'failure_code', 'schema_or_generation_failure')
            state['feedback'] = {'failure_code': code, 'schema_errors': schema_errors(error),
                                 'instruction': 'Repair the complete section using draft_contract. Use a nonempty sentences list with complete supported points and only allowed source IDs.'}
            log.warning('summary_section index=%s attempt=%s failure_code=%s error_type=%s',
                        part['index'], state['attempts'], code, type(error).__name__)
        state['last_draft'] = draft

    for state in states:
        if stopped():
            break
        write(state)
    for _ in range(MAX_REPAIRS):
        if stopped():
            break
        if overall_check()['valid'] and all(s['points'] for s in states):
            break
        short = overall_check()['actual_words'] < request['target_words']
        candidates = [s for s in states if s['attempts'] == 1 and not section_check(s)['valid']
                      and (section_check(s)['actual_words'] < s['plan']['target_words']) == short]
        if not candidates:
            break
        write(max(candidates, key=lambda s: length_distance(section_check(s))))
    points = combined()
    if not points:
        log.info('summary_expansion=finished actual_words=0 target_words=%s writing_calls=%s valid=False '
                 'verification_unavailable=%s connection_unavailable=%s',
                 request['target_words'], writing_calls, verification_unavailable, connection_unavailable)
        return None
    # Preserve topic boundaries in ordinary prose, without inserting unverified
    # model-generated outline headings into the student answer.
    text = ('\n\n'.join(render_points(state['points'], part_request(state)) for state in states if state['points'])
            if request['layout'] == 'prose' and not request.get('target_paragraphs')
            else render_points(points, request))
    check = length_check(text, request)
    complete = check['valid'] and all(s['points'] for s in states)
    log.info('summary_expansion=finished actual_words=%s target_words=%s writing_calls=%s valid=%s '
             'verification_unavailable=%s connection_unavailable=%s',
             check['actual_words'], request['target_words'], writing_calls, check['valid'],
             verification_unavailable, connection_unavailable)
    return source_section(text), {'valid': True, 'stage': 'summary_section_expansion',
        'response_mode': 'generated' if complete else 'checked_points', 'length_validation': check,
        'writing_calls': writing_calls, 'section_count': len(plan),
        'grounding_validation': {'valid': True, 'results': [
            {'claim': p['text'], 'citations': p['citation_ids'], 'supported': True} for p in points]}}
