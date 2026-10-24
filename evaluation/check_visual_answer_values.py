"""Answer-value formatting and precise, content-free validation errors."""
import json
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from backend.visual_reasoning import VisualSolution, solve_image_problem
from backend.visual_tasks import literal_visual_numbers, prose_citations


class VisualAnswerValuesChecks(unittest.TestCase):
    def test_valid_numeric_answer_values_do_not_raise_root_validation_error(self):
        for text in ('The result is [2].', 'Matching IDs: [2, 4, 7].', 'Indices [0–3] are included.',
                     'Array values are [[1,2], [3,4]].', 'The selected label is 【2】.'):
            with self.subTest(text=text):
                solved = VisualSolution(answerable=True, explanation=text, limitations=[])
                rendered = literal_visual_numbers(solved.explanation)
                self.assertFalse(prose_citations(rendered))
                self.assertEqual(rendered.replace('`',''), text)

    def test_formatting_preserves_code_and_is_idempotent(self):
        text = '''The output is [2]. Use `rows[1]`.
```sql
SELECT ARRAY[1,2] FROM matches;
```
~~~python
values = [3,4]
~~~
````text
literal [5]
````
'''
        formatted = literal_visual_numbers(text)
        self.assertIn('The output is `[2]`.', formatted)
        self.assertIn('Use `rows[1]`.', formatted)
        self.assertIn('SELECT ARRAY[1,2] FROM matches;', formatted)
        self.assertIn('values = [3,4]', formatted)
        self.assertIn('literal [5]', formatted)
        self.assertEqual(literal_visual_numbers(formatted), formatted)

    def test_empty_limitation_items_are_omitted_without_dropping_real_uncertainty(self):
        value = VisualSolution(answerable=True, explanation='A complete answer.',
            limitations=['', ' ', 'A row label is unclear.', '\n\t'])
        self.assertEqual(value.limitations, ['A row label is unclear.'])

    def test_blank_explanation_has_a_specific_error_type(self):
        with self.assertRaises(ValidationError) as error:
            VisualSolution(answerable=True, explanation=' \n ', limitations=[])
        self.assertEqual(error.exception.errors(include_input=False)[0]['type'], 'visual_blank_explanation')

    def test_boolean_and_structural_validation_remain_strict(self):
        for payload in ({'answerable':'true','explanation':'Text','limitations':[]},
                        {'answerable':True,'explanation':'Text','limitations':[None]},
                        {'answerable':True,'explanation':'Text'},
                        {'answerable':True,'explanation':'Text','limitations':[], 'image':99}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                VisualSolution.model_validate(payload)

    def test_blank_answer_retry_gets_specific_feedback_without_logging_private_text(self):
        client = Mock()
        for method in ('for_task','for_summary','with_output_budget'):
            getattr(client,method).return_value=client
        client.generate_json.return_value = {'answerable':True,'explanation':' \n ','limitations':[]}
        secret='PRIVATE-VISIBLE-QUESTION-DO-NOT-LOG'
        with patch('backend.visual_reasoning.LLM',return_value=client), \
             self.assertLogs('backend.visual_reasoning',level='WARNING') as logs:
            with self.assertRaises(HTTPException):
                solve_image_problem(secret, {'observations':[{'image':1,'text':secret}], 'limitations':[]})
        self.assertEqual(client.generate_json.call_count,2)
        self.assertIn('visual_blank_explanation', '\n'.join(logs.output))
        self.assertNotIn(secret, '\n'.join(logs.output))
        retry = json.loads(client.generate_json.call_args_list[1].args[0])
        self.assertIn('nonblank answer',retry['revision_requirement'])

    def test_large_valid_answer_keeps_all_data_after_inline_formatting(self):
        from backend.multi_image_tutor import ImagesDraft
        raw='[1]' * 1500
        VisualSolution(answerable=True, explanation=raw, limitations=[])
        formatted=literal_visual_numbers(raw)
        draft=ImagesDraft(answerable=True, observations=[], explanation=formatted, limitations=[])
        self.assertEqual(len(draft.explanation),7500)
        self.assertEqual(draft.explanation.replace('`',''),raw)
