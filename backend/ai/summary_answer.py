"""Summary drafts and source-preserving recovery without unverified prose."""
import re

from pydantic import Field
from backend.ai.answer_contract import StrictModel, AnswerSection, citation_ids
from backend.ai.answer_quality import wrong_script
from backend.ai.response_request import length_check


class SummarySentence(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    citation_ids: list[int] = Field(min_length=1, max_length=8)


class SummaryDraft(StrictModel):
    sentences: list[SummarySentence] = Field(min_length=1, max_length=192)

    def render(self, source_count, request=None):
        request = request or {'max_sentences': 8, 'long_form': False, 'layout': 'prose'}
        if len(self.sentences) > request['max_sentences']:
            raise ValueError('Summary exceeded the requested sentence budget.')
        sentences = []
        for item in self.sentences:
            if not item.text.strip() or citation_ids(item.text) or any(
                not 1 <= n <= source_count for n in item.citation_ids
            ):
                raise ValueError('Invalid summary text or source number.')
            refs = ''.join(f'[{n}]' for n in dict.fromkeys(item.citation_ids))
            sentences.append(item.text.strip().rstrip('.!?') + ' ' + refs + '.')
        if request.get('layout') == 'bullets':
            return '\n'.join('- ' + s for s in sentences)
        if request.get('layout') == 'table':
            return '| Point | Explanation |\n| --- | --- |\n' + '\n'.join(
                f'| {i} | {s.replace("|", " / ")} |' for i, s in enumerate(sentences, 1))
        groups = request.get('target_paragraphs') or (max(2, round(len(sentences) / 6)) if request.get('long_form') else 1)
        size = max(1, (len(sentences) + groups - 1) // groups)
        return '\n\n'.join(' '.join(sentences[i:i + size]) for i in range(0, len(sentences), size))


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
        if (5 <= len(block.split()) <= 100 and not citation_ids(block)
            and not wrong_script(block, question)):
            assert block in content
            return block
    return None


def recover_summary(sources, checks, question, request=None):
    # Each verifier result approves only its own sentence and citation list.
    # Do not concatenate a failed draft or inherit its uncited introductions.
    for check in reversed(checks):
        sentences, seen = [], set()
        for item in check.get('grounding_validation', {}).get('results', []):
            claim = item.get('claim')
            numbers = item.get('citations') or [item.get('citation')]
            if (item.get('supported') is not True or not isinstance(claim, str)
                or not claim.strip() or len(claim) > 1000 or citation_ids(claim)
                or wrong_script(claim, question) or not numbers
                or any(type(n) is not int or not 1 <= n <= len(sources) for n in numbers)
                or re.match(r'^(?:it|this|these|those|they|their|such|therefore|thus|consequently)\b', claim, re.I)):
                continue
            key = ' '.join(claim.casefold().split())
            if key in seen:
                continue
            seen.add(key)
            sentences.append({'text': claim.rstrip('.!?'), 'citation_ids': list(dict.fromkeys(numbers))})
            if len(sentences) == (request['max_sentences'] if request and request['long_form'] else 6):
                break
        if sentences:
            text = SummaryDraft.model_validate({'sentences': sentences}).render(len(sources), request)
            validation = {
                'valid': True, 'stage': 'summary_checked_points',
                'response_mode': 'checked_points', 'supported_sentence_count': len(sentences),
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
