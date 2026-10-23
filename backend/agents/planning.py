"""Deterministic progress controls around model-selected agent actions."""
import json
import re
import unicodedata
from backend.agents.contracts import Decision, requested_days

MAX_SEARCHES = 2


class ActionRejected(ValueError):
    def __init__(self, code, **details):
        self.code, self.details = code, details
        super().__init__(code)


def action_key(action):
    value = action.model_dump()
    if action.tool == 'document_search':
        value['query'] = ' '.join(re.findall(r'\w+', unicodedata.normalize('NFKC', action.query).casefold()))
    return json.dumps(value, sort_keys=True)


def current_tools(request, permitted, trace, remaining_steps):
    tools = set(permitted)
    names = [entry['tool'] for entry in trace]
    counts = {tool: names.count(tool) for tool in tools}
    for tool, limit in [('document_search', MAX_SEARCHES), ('memory_read', 1), ('task_list', 1)]:
        if counts.get(tool, 0) >= limit:
            tools.discard(tool)
    if request.skill == 'research_brief' and 'document_search' not in names:
        tools.discard('finish')
    if request.skill == 'study_plan' and requested_days(request.goal) is not None:
        tools -= {'finish', 'task_create'}
        if 'document_search' not in names:
            return {'document_search'}
    if remaining_steps <= 2 and trace:
        closing = tools & {'study_plan_create', 'finish'}
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
    refs = action.references if action.tool == 'finish' else (
        [ref for day in action.days for ref in day.references] if action.tool == 'study_plan_create' else [])
    if not set(refs) <= references:
        raise ActionRejected('unknown_reference', available_references=sorted(references))
    target = requested_days(request.goal)
    if action.tool == 'study_plan_create' and target is not None and len(action.days) != target:
        raise ActionRejected('day_count_mismatch', expected_days=target)


def compact_observations(observations):
    result, documents = [], {}
    for item in observations:
        if item.get('tool') == 'document_search':
            for passage in item['data'].get('passages', []):
                documents.setdefault(passage['reference'], {**passage, 'text': passage.get('text', '')[:600]})
        else:
            result.append(item)
    if documents:
        result.insert(0, {'tool': 'document_search', 'data': {'passages': list(documents.values())[:8]}, 'untrusted_data': True})
    return result


def plan_result(action, observation):
    text = action.overview + '\n\n' + '\n\n'.join(
        f'Day {day.day}: {day.title}\n{day.details}' +
        ('\nReferences: ' + ', '.join(day.references) if day.references else '') for day in action.days)
    return {'text': text, 'references': sorted({ref for day in action.days for ref in day.references}),
            'verified': False, 'provenance': 'agent_draft', 'structured_plan': action.model_dump(),
            'task_ids': [item['id'] for item in observation['tasks']]}
