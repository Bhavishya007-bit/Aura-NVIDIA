"""Deterministic progress controls around model-selected agent actions."""
import json
import re
import unicodedata
from backend.agents.contracts import Decision, requested_days, requested_questions
from backend.agents.web import MAX_WEB_SEARCHES

MAX_SEARCHES = 2


def parse_decision(raw):
    """Normalize unambiguous JSON envelopes, then apply the unchanged strict schema.

    JSON-object mode does not enforce the schema. Some models return a flat tool
    call or nest its arguments even when asked for Aura's decision envelope.
    Never discard unknown fields, guess arguments, or choose a tool here.
    """
    if not isinstance(raw, dict):
        return Decision.model_validate(raw)
    value = dict(raw)
    if 'action' not in value and isinstance(value.get('tool'), str):
        value = {'action': {key: item for key, item in value.items() if key != 'plan'},
                 **({'plan': value['plan']} if 'plan' in value else {})}
    elif isinstance(value.get('action'), str) and 'tool' not in value:
        value = {'action': {'tool': value['action'],
                           **{key: item for key, item in value.items() if key not in {'action', 'plan'}}},
                 **({'plan': value['plan']} if 'plan' in value else {})}
    action = value.get('action')
    if isinstance(action, dict):
        for wrapper in ('arguments', 'parameters'):
            if (set(action) == {'tool', wrapper} and isinstance(action[wrapper], dict)
                    and 'tool' not in action[wrapper]):
                value['action'] = {'tool': action['tool'], **action[wrapper]}
                break
    # This is a display-only intention, never an inferred tool action/argument.
    if 'plan' not in value:
        value['plan'] = ['Use the selected study tool.']
    elif isinstance(value['plan'], str):
        value['plan'] = [value['plan']]
    return Decision.model_validate(value)


class ActionRejected(ValueError):
    def __init__(self, code, **details):
        self.code, self.details = code, details
        super().__init__(code)


def action_key(action):
    value = action.model_dump()
    if action.tool in {'document_search', 'web_search'}:
        value['query'] = ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', action.query).casefold()))
    return json.dumps(value, sort_keys=True)


def current_tools(request, permitted, trace, remaining_steps):
    tools = set(permitted)
    names = [entry['tool'] for entry in trace]
    counts = {tool: names.count(tool) for tool in tools}
    for tool, limit in [('document_search', MAX_SEARCHES), ('web_search', MAX_WEB_SEARCHES), ('code_execute', 2), ('memory_read', 1), ('task_list', 1)]:
        if counts.get(tool, 0) >= limit:
            tools.discard(tool)
    if request.skill == 'research_brief':
        if 'document_search' not in names:
            tools.discard('finish')
            tools.discard('web_search')
        elif 'web_search' in permitted and 'web_search' not in names:
            return {'web_search'}  # Gather both source types before writing.

    if request.skill == 'assessment':
        tools.discard('finish')
        if 'document_search' not in names:
            return {'document_search'}

    if request.skill == 'code_analysis':
        if request.source_id is None:
            tools.discard('document_search')
        if 'code_execute' not in names:
            tools.discard('finish')
        elif counts.get('code_execute', 0) >= 2:
            return {'finish'}

    if request.skill == 'study_plan' and requested_days(request.goal) is not None:
        tools -= {'finish', 'task_create'}
        if 'document_search' not in names:
            return {'document_search'}
    if remaining_steps <= 2 and trace:
        closing = tools & {'study_plan_create', 'assessment_create', 'finish'}
        if closing:
            tools = closing
    return tools


def action_schema(tools):
    schema = Decision.model_json_schema()
    action = schema['properties']['action']
    mapping = action['discriminator']['mapping']
    mapping = {key: ref for key, ref in mapping.items() if key in tools}
    action['discriminator']['mapping'] = mapping
    action['oneOf'] = [item for item in action['oneOf'] if item['$ref'] in mapping.values()]
    # Keep only transitively reachable definitions to bound repeated prompt cost.
    definitions, needed = schema.pop('$defs'), set()
    def visit(node):
        if isinstance(node, dict):
            ref = node.get('$ref', '')
            if ref.startswith('#/$defs/') and ref.rsplit('/', 1)[-1] not in needed:
                name = ref.rsplit('/', 1)[-1]
                needed.add(name)
                visit(definitions[name])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    schema['$defs'] = {key: value for key, value in definitions.items() if key in needed}
    return schema


def validate_action(action, tools, seen_actions, references, request):
    if action.tool not in tools:
        raise ActionRejected('tool_not_available', allowed_tools=sorted(tools))
    if action.tool != 'finish' and action_key(action) in seen_actions:
        raise ActionRejected('duplicate_action', instruction='Do not repeat the same action. Move to planning or completion.')
    refs = list(action.references) if action.tool == 'finish' else (
        [ref for day in action.days for ref in day.references] if action.tool == 'study_plan_create' else
        [ref for question in action.questions for ref in question.references] if action.tool == 'assessment_create' else [])
    if action.tool == 'assessment_create':
        if any(not ref.startswith('D') for ref in refs):
            raise ActionRejected('source_type_mismatch')
        count = requested_questions(request.goal)
        if count is not None and len(action.questions) != count:
            raise ActionRejected('question_count_mismatch', expected_questions=count)
    if action.tool == 'finish':
        for field, prefix in [('from_material', 'D'), ('from_web', 'W')]:
            section = getattr(action, field)
            if section:
                if request.skill != 'research_brief' or any(not ref.startswith(prefix) for ref in section.references):
                    raise ActionRejected('source_type_mismatch')
                refs.extend(section.references)
                inline = set(re.findall(r'\[((?:D|W)[a-zA-Z0-9]+)\]', section.text))
                if not inline <= set(section.references):
                    raise ActionRejected('unknown_reference')
        if request.skill == 'research_brief' and any(ref.startswith('W') for ref in references) and not (action.from_material or action.from_web):
            raise ActionRejected('research_sections_required', instruction='Separate uploaded and web findings into from_material and from_web. Omit irrelevant findings and explain that in limitations.')
        if request.skill == 'research_brief' and any(ref.startswith('W') for ref in refs) and not action.from_web:
            raise ActionRejected('research_sections_required', instruction='Put web findings in from_web with observed web references.')
    if not set(refs) <= references:
        raise ActionRejected('unknown_reference', available_references=sorted(references))
    target = requested_days(request.goal)
    if action.tool == 'study_plan_create' and target is not None and len(action.days) != target:
        raise ActionRejected('day_count_mismatch', expected_days=target)


def compact_observations(observations):
    result, documents, web, previous_questions = [], {}, {}, []
    for item in observations:
        if item.get('tool') == 'document_search':
            previous_questions.extend(item['data'].get('previous_questions', []))
            for passage in item['data'].get('passages', []):
                documents.setdefault(passage['reference'], {**passage, 'text': passage.get('text', '')[:600]})
        elif item.get('tool') == 'web_search':
            for passage in item['data'].get('passages', []):
                web.setdefault(passage['reference'], {**passage, 'text': passage.get('text', '')[:900]})
            result.append({**item, 'data': {k: v for k, v in item['data'].items() if k != 'passages'}})
        elif item.get('tool') == 'code_execute':
            from backend.agents.sandbox import public_output
            data = public_output(item['data'])
            data['stdout'], data['stderr'] = data.get('stdout', '')[:4096], data.get('stderr', '')[:4096]
            result.append({**item, 'data': data, 'untrusted_data': True})
        else:
            result.append(item)
    if web:
        result.insert(0, {'tool': 'web_search', 'data': {'passages': list(web.values())[:8]}, 'untrusted_data': True})
    if documents:
        result.insert(0, {'tool': 'document_search', 'data': {'passages': list(documents.values())[:8],
            **({'previous_questions': list(dict.fromkeys(previous_questions))[:10]} if previous_questions else {})}, 'untrusted_data': True})
    return result


def plan_result(action, observation):
    text = action.overview + '\n\n' + '\n\n'.join(
        f'Day {day.day}: {day.title}\n{day.details}' +
        ('\nReferences: ' + ', '.join(day.references) if day.references else '') for day in action.days)
    return {'text': text, 'references': sorted({ref for day in action.days for ref in day.references}),
            'verified': False, 'provenance': 'agent_draft', 'structured_plan': action.model_dump(),
            'task_ids': [item['id'] for item in observation['tasks']]}


def research_result(action, observations):
    """Build provenance from observed data, never model-written source URLs."""
    sources, statuses = {}, []
    for item in observations:
        if item['tool'] not in {'document_search', 'web_search'}:
            continue
        data = item['data']
        if item['tool'] == 'web_search':
            statuses.append(data.get('status', 'unavailable'))
        for passage in data.get('passages', []):
            sources[passage['reference']] = {k: v for k, v in passage.items() if k != 'text'} | {
                'kind': 'web' if item['tool'] == 'web_search' else 'material'}
    sections = []
    for field, kind in [('from_material', 'material'), ('from_web', 'web')]:
        value = getattr(action, field)
        if value:
            sections.append({'kind': kind, **value.model_dump()})
    if not sections and action.answer.strip() and action.references:
        sections = [{'kind': 'material', 'text': action.answer, 'references': action.references}]
    refs = sorted({ref for section in sections for ref in section['references']})
    limitations = [value.strip()[:500] for value in action.limitations if value.strip()]
    status = ('searched' if 'searched' in statuses else 'no_results' if 'no_results' in statuses
              else 'unavailable' if statuses else 'not_configured')
    if not any(section['kind'] == 'material' for section in sections):
        limitations.append('No material-backed findings were included from the passages checked.')
    if status == 'searched' and not any(section['kind'] == 'web' for section in sections):
        limitations.append('No web-backed findings were included in this brief.')
    if status != 'searched':
        limitations.insert(0, {'no_results': 'Web search returned no usable sources.',
                              'unavailable': 'Web search was unavailable; this brief uses uploaded material only.',
                              'not_configured': 'Web search is not configured; this brief uses uploaded material only.'}[status])
    labels = {'material': 'From your material', 'web': 'From the web'}
    text = '\n\n'.join('## ' + labels[s['kind']] + '\n\n' + s['text'] for s in sections)
    if not sections:
        text = 'No source-backed findings were returned. Try a more specific topic.'
    if limitations:
        text += '\n\n## Limitations\n\n' + '\n'.join('- ' + value for value in limitations[:5])
    return {'text': text, 'references': refs, 'verified': False, 'provenance': 'agent_draft',
            'research_sections': sections, 'sources': [sources[ref] for ref in refs if ref in sources],
            'web_status': status, 'limitations': limitations[:5]}
