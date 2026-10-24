"""Summary drafts and source-preserving recovery without unverified prose."""
import re

from pydantic import Field
from backend.ai.answer_contract import StrictModel, AnswerSection, citation_ids, CITATIONS, has_noncanonical_citations
from backend.ai.answer_quality import wrong_script
from backend.ai.response_request import length_check


class SummaryDraftError(ValueError):
    """Safe format feedback: codes/indices only, never document or model text."""

    def __init__(self, code, *, sentence_index=None):
        super().__init__(code)
        self.failure_code = code
        self.feedback = {'code': code, 'sentence_index': sentence_index}


class SummarySentence(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    citation_ids: list[int] = Field(min_length=1, max_length=8)


class SummaryDraft(StrictModel):
    sentences: list[SummarySentence] = Field(min_length=1, max_length=192)

    def points(self, source_count, request=None):
        request = request or {'max_sentences': 8, 'long_form': False, 'layout': 'prose'}
        if len(self.sentences) > request['max_sentences']:
            raise SummaryDraftError('sentence_budget_exceeded')
        points = []
        for index, item in enumerate(self.sentences):
            if has_noncanonical_citations(item.text):
                raise SummaryDraftError('noncanonical_citation_marker', sentence_index=index)
            if any(not 1 <= n <= source_count for n in item.citation_ids):
                raise SummaryDraftError('citation_out_of_range', sentence_index=index)
            inline = citation_ids(item.text)
            if any(n not in item.citation_ids for n in inline):
                raise SummaryDraftError('citation_metadata_mismatch', sentence_index=index)
            # Redundant matching markers are formatting, not new evidence.
            # Canonicalize them before the unchanged factual-support checks.
            text = CITATIONS.sub('', item.text).strip()
            if not text:
                raise SummaryDraftError('empty_sentence', sentence_index=index)
            if inline:
                text = re.sub(r'[ \t]+([.,;:!?])', r'\1', text)
            if not standalone_point(text, allow_anaphora=True):
                raise SummaryDraftError('incomplete_sentence', sentence_index=index)
            points.append({'text': text.rstrip('.!?'), 'citation_ids': list(dict.fromkeys(item.citation_ids))})
        return points

    def render(self, source_count, request=None):
        request = request or {'max_sentences': 8, 'long_form': False, 'layout': 'prose'}
        sentences = [item['text'] + ' ' + ''.join(f'[{n}]' for n in item['citation_ids']) + '.'
                     for item in self.points(source_count, request)]
        if request.get('layout') == 'bullets':
            return '\n'.join('- ' + s for s in sentences)
        if request.get('layout') == 'table':
            return '| Point | Explanation |\n| --- | --- |\n' + '\n'.join(
                f'| {i} | {s.replace("|", " / ")} |' for i, s in enumerate(sentences, 1))
        groups = request.get('target_paragraphs') or (max(2, round(len(sentences) / 6)) if request.get('long_form') else 2 if len(sentences) > 4 else 1)
        size = max(1, (len(sentences) + groups - 1) // groups)
        return '\n\n'.join(' '.join(sentences[i:i + size]) for i in range(0, len(sentences), size))


def standalone_point(text, *, allow_anaphora=False):
    """Reject obvious damaged fragments without splitting scientific abbreviations."""
    if not allow_anaphora and re.match(r'^(?:it|this|these|those|they|their|such|therefore|thus|consequently)\b', text.strip(), re.I):
        return False
    balance = 0
    for char in text:
        if char == '(':
            balance += 1
        elif char == ')':
            balance -= 1
            if balance < 0:
                return False
    return balance == 0


def summary_contract(request, source_count):
    """Expose the same bounds to generation and validation, including long requests."""
    schema = SummaryDraft.model_json_schema()
    schema['properties']['sentences']['maxItems'] = request['max_sentences']
    items = schema['$defs']['SummarySentence']['properties']['citation_ids']['items']
    items.update(minimum=1, maximum=source_count)
    target = request.get('target_words')
    return {'output_schema': schema, 'target_words': target,
            'minimum_words': max(1, int(target * .9)) if target else None,
            'maximum_words': int(target * 1.1) if target else None,
            'suggested_sentence_count': min(request['max_sentences'], max(1, round(target / 25))) if target else None,
            'instruction': ('Write a connected explanation at the requested length using only supported '
                'points from the supplied passages. Word counts apply to all text fields combined, '
                'excluding citations and JSON syntax. Do not return an empty sentences list. '
                'A length request does not mean the material is missing. Prefer substantive teaching '
                'content to OCR headers, copyright notices and extraction metadata.')}


def source_section(text):
    return AnswerSection(kind='sourced', text=text, provenance='uploaded_material',
                         verified=True, citation_ids=citation_ids(text))


def literal_excerpt(content, question):
    """Keep contiguous lines together: wrapped headings must not lose their end."""
    lines = content.splitlines(keepends=True)
    wrapper = re.compile(
        r'^(?:Slide \d+:|Slide text:|(?:Image|Page|Slide) \d+ recognized|'
        r'<number>|Figure\s|Copyright|\u00a9|DjVu|LIZARDTECH)', re.I)
    for index, line in enumerate(lines):
        if not line.strip() or wrapper.match(line.strip()) or not re.search(r'[A-Za-z]', line):
            continue
        block = ''
        for following in lines[index:index + 12]:
            if wrapper.match(following.strip()) or len(block) + len(following) > 600:
                break
            block += following
        block = block.strip()
        if (5 <= len(block.split()) <= 100 and not citation_ids(block) and not has_noncanonical_citations(block)
            and not wrong_script(block, question)):
            assert block in content
            return block
    return None


def checked_points(sources, check, question, request=None):
    """Retain whole approved units, never a substring split out of a sentence."""
    sentences, seen = [], set()
    for item in check.get('grounding_validation', {}).get('results', []):
        claim = item.get('claim')
        numbers = item.get('citations') or [item.get('citation')]
        if (item.get('supported') is not True or not isinstance(claim, str)
            or not claim.strip() or len(claim) > 1000 or citation_ids(claim) or has_noncanonical_citations(claim)
            or wrong_script(claim, question) or not numbers
            or any(type(n) is not int or not 1 <= n <= len(sources) for n in numbers)
            or not standalone_point(claim)):
            continue
        key = ' '.join(claim.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        sentences.append({'text': claim.rstrip('.!?'), 'citation_ids': list(dict.fromkeys(numbers))})
        if len(sentences) == (request['max_sentences'] if request and request['long_form'] else 6):
            break
    return sentences


def recover_summary(sources, checks, question, request=None):
    # Each verifier result approves only its own sentence and citation list.
    # Do not concatenate a failed draft or inherit its uncited introductions.
    for check in reversed(checks):
        sentences = checked_points(sources, check, question, request)
        if sentences:
            text = SummaryDraft.model_validate({'sentences': sentences}).render(len(sources), request)
            validation = {
                'valid': True, 'stage': 'summary_checked_points',
                'response_mode': 'checked_points', 'supported_sentence_count': len(sentences),
                'grounding_validation': {'valid': True, 'results': [
                    {'claim': p['text'], 'citations': p['citation_ids'], 'supported': True} for p in sentences]},
            }
            if request:
                validation['length_validation'] = length_check(text, request)
            return source_section(text), validation

    # When a judge/model is down, literal membership still proves a quote's
    # origin. Excerpts are explicitly labelled and never passed off as synthesis.
    excerpts, seen, locations = [], set(), set()
    for number, source in enumerate(sources, 1):
        location = (source.get('source_id'), source.get('page'), source.get('slide'), source.get('timestamp_start'))
        if location == (source.get('source_id'), None, None, None):
            location = ('chunk', source.get('chunk_id', number))
        if location in locations:
            continue
        text = literal_excerpt(source.get('content', ''), question)
        if text:
            key = ' '.join(text.casefold().split())
            if key in seen:
                continue
            # No rewriting, whitespace collapse, or filling missing information.
            assert text in source['content']
            excerpts.append(f'“{text}” [{number}]')
            seen.add(key)
            locations.add(location)
        if len(excerpts) == 6 or sum(map(len, excerpts)) >= 1800:
            break
    if excerpts:
        return source_section(' '.join(excerpts)), {
            'valid': True, 'stage': 'summary_source_excerpts', 'response_mode': 'extractive',
            'proof': 'Each quotation is an exact substring of its cited passage.',
        }
    return None, {'valid': False, 'stage': 'summary_no_readable_evidence'}
