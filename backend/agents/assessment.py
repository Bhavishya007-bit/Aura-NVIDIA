"""Adapt agent MCQ drafts to Aura's existing saved-assessment contract."""
from backend.study_tools import GenerateRequest, attach_source_evidence, validate_items


def assessment_payload(run, action, steps, history):
    observed = {}
    for step in steps:
        if step.get('tool') == 'document_search' and step.get('state') == 'completed':
            for passage in step.get('observation', {}).get('passages', []):
                observed[passage['reference']] = passage
    refs = sorted({ref for question in action.questions for ref in question.references})
    # The executor repeats runtime checks against persisted observations.
    if not refs or any(ref not in observed or not ref.startswith('D') for ref in refs):
        raise ValueError('Unknown assessment reference.')
    citations = []
    for index, ref in enumerate(refs, 1):
        passage = observed[ref]
        citations.append({'id': index, 'chunk_id': int(ref[1:]), 'source_id': passage.get('source_id', run['source_id']),
            'title': passage.get('title', 'Selected material'), 'page': passage.get('page'),
            'slide': passage.get('slide'), 'seconds': None, 'topic_id': None,
            'location': (f"Slide {passage['slide']}" if passage.get('slide') else
                         f"Page {passage['page']}" if passage.get('page') else 'Selected material'),
            'excerpt': passage['text']})
    ids = {ref: index for index, ref in enumerate(refs, 1)}
    raw_items = []
    for question in action.questions:
        value = question.model_dump(exclude={'references'})
        value['citation_ids'] = [ids[ref] for ref in question.references]
        value['answer'] = next((choice.text for choice in question.choices if choice.id == question.correct_choice_id), '')
        raw_items.append(value)
    request = GenerateRequest(course_id=run['course_id'], source_id=run['source_id'], kind='assessment',
        count=len(raw_items), focus=action.focus, difficulty=action.difficulty, learning_mode='manual')
    items = validate_items(attach_source_evidence({'items': raw_items}, citations), request, citations, set(), history)
    return {'material_ids': run['request'].get('material_ids') or [run['source_id']], 'agent_run_id': str(run['id']), 'source_id': run['source_id'], 'course_id': run['course_id'],
        'source_title': citations[0]['title'], 'title': action.title, 'focus': action.focus,
        'items': items, 'citations': citations,
        'coverage': {'selected_passages': len(citations), 'available_passages': len(observed)},
        'verification': 'model_checked', 'quality_version': 'agent-assessment-v1',
        'learning': {'mode': 'manual', 'difficulty': action.difficulty,
                     'reason': 'Quiz created from your selected material and goal.'},
        'fulfillment': {'requested': len(items), 'created': len(items), 'partial': False}, 'notice': ''}


def assessment_result(run, action):
    count = len(action.questions)
    return {'text': f'Your {count}-question quiz is ready. Open Assessment to answer it and get feedback.',
        'references': sorted({ref for question in action.questions for ref in question.references}),
        'verified': False, 'provenance': 'model_checked_assessment',
        'assessment': {'artifact_id': str(run['id']), 'title': action.title, 'question_count': count,
                       'difficulty': action.difficulty, 'focus': action.focus, 'verification': 'model_checked'}}
