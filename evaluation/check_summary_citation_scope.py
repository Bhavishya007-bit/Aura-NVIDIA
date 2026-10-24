"""Explicit local citation protocols, not guessed repairs of foreign citations."""
import copy
import json
import unittest
from unittest.mock import Mock

from backend.ai.citation_grounding import CitationGrounding
from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from evaluation.check_long_answers import DocumentRetriever, HISTORY, LengthLLM, long_fixture


class LocalCitationLLM(LengthLLM):
    def __init__(self):
        super().__init__()
        self.rows, self.full = long_fixture()

    def generate_json(self, data, max_retries=2, system_prompt=None):
        if 'SELECTED uploaded material' in (system_prompt or ''):
            payload = json.loads(data)
            if 'section_request' not in payload:
                self.calls.append(('whole', payload, system_prompt))
                return {'sentences': copy.deepcopy(self.full['sentences'][:8])}
            self.calls.append(('section', payload, system_prompt))
            # Reproduce a model citing each supplied portion as 1..N.
            points = []
            for point in self.full['sentences']:
                ids = [i for i, source in enumerate(payload['passages'], 1) if point['text'] in source['text']]
                if ids:
                    points.append({'text': point['text'], 'citation_ids': ids})
            return {'sentences': points}
        return super().generate_json(data, max_retries, system_prompt)


class CitationScope(unittest.TestCase):
    def test_local_section_citations_map_back_to_the_actual_owned_passages(self):
        llm = LocalCitationLLM()
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(result['length_validation']['valid'], result['length_validation'])
        self.assertEqual(result['length_validation']['actual_words'], 2000)
        sections = [row[1] for row in llm.calls if row[0]=='section']
        self.assertEqual(len(sections), 4)
        for section in sections:
            ids = [source['id'] for source in section['passages']]
            self.assertEqual(ids, list(range(1, len(ids)+1)))
            self.assertEqual(section['section_request']['source_ids'], ids)
            self.assertTrue(all(set(point)=={'text'} for point in section['already_explained']))
            self.assertNotIn('conversation_context', section)
        checks = result['citation_validation']['source_validation']['grounding_validation']['results']
        for checked in checks:
            self.assertTrue(all(checked['claim'] in result['sources'][number-1]['content'] for number in checked['citations']))
        self.assertIn(39, result['sections'][0]['citation_ids'])

    def test_long_writing_prompt_does_not_include_the_brief_summary_default(self):
        llm = LocalCitationLLM()
        SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        prompts = [row[2] for row in llm.calls if row[0] in ('whole','section')]
        self.assertTrue(prompts)
        self.assertTrue(all('4–6 sentences' not in prompt for prompt in prompts))
        self.assertTrue(all('One short supported sentence' not in prompt for prompt in prompts))

    def test_sparse_claim_indices_use_a_contiguous_wire_protocol_and_explicit_mapping(self):
        llm = Mock()
        llm.generate_json.return_value = {'results': [
            {'id':3,'supported':True,'reason':'Third'},
            {'id':1,'supported':True,'reason':'First'},
            {'id':2,'supported':False,'reason':'Second'}]}
        items = [{'id':number,'claim':f'Claim {number}','evidence':'Supplied evidence.'} for number in (7,19,37)]
        result = CitationGrounding(llm)._verify_batch(items)
        self.assertEqual(set(result), {7,19,37})
        self.assertTrue(result[7]['supported'])
        self.assertFalse(result[19]['supported'])
        self.assertTrue(result[37]['supported'])
        payload = json.loads(llm.generate_json.call_args.args[0].split('BATCH_CLAIMS_DATA: ',1)[1])
        self.assertEqual([row['id'] for row in payload], [1,2,3])

    def test_malformed_batch_still_rejects_every_claim_and_logs_no_private_data(self):
        invalid = ({'results':[]},
                   {'results':[{'id':1,'supported':True},{'id':1,'supported':True}]},
                   {'results':[{'id':1,'supported':True},{'id':99,'supported':True}]},
                   {'results':[{'id':1,'supported':'yes'},{'id':2,'supported':True}]})
        items = [{'id':9,'claim':'PRIVATE_CLAIM','evidence':'PRIVATE_EVIDENCE'},
                 {'id':20,'claim':'Other claim','evidence':'Other evidence'}]
        for raw in invalid:
            with self.subTest(raw=raw):
                llm = Mock(); llm.generate_json.return_value = raw
                with self.assertLogs('backend.ai.citation_grounding', 'WARNING') as logs:
                    result = CitationGrounding(llm)._verify_batch(items)
                self.assertTrue(all(row.get('error')=='verification_unavailable' and not row['supported'] for row in result.values()))
                self.assertNotIn('PRIVATE', '\n'.join(logs.output))

