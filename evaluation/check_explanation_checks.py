"""Concrete contradiction regressions, not a universal language/correctness score."""
from pathlib import Path
import unittest
from backend.agents.explanation_checks import explanation_findings


class ExplanationConsistency(unittest.TestCase):
    def test_actual_accepted_answer_has_two_independent_contradictions(self):
        answer=(Path(__file__).parent/'fixtures'/'search_answer_reviewer_miss.md').read_text()
        findings=explanation_findings(answer)
        self.assertEqual({row['rule'] for row in findings},{'numeric_list_position','comparison_counterexample'})
        middle=next(row for row in findings if row['rule']=='numeric_list_position')
        self.assertEqual(middle['claimed_value'],'23')
        self.assertEqual(middle['matching_indices'],[5])
        self.assertEqual(middle['expected_values'],['16'])

    def test_direct_reverse_bullet_and_parallel_labels_are_checked(self):
        start='The sorted list is [2,5,8,12,16,23,38,42,50].\n'
        for claim in ('23 is the middle element.', 'The middle value is 23.',
                      '- `23` (middle element)', 'The targets [2,23,50,7] (first,middle,last,absent).'):
            with self.subTest(claim=claim):
                self.assertEqual(explanation_findings(start+claim)[0]['expected_values'],['16'])
        for claim in ('16 is the middle element.','The middle value is 16.',
                      'The targets [2,16,50,7] (first,middle,last,absent).'):
            self.assertEqual(explanation_findings(start+claim),[])

    def test_first_last_absent_duplicates_and_even_middle_values(self):
        text='The array [1,3,3,9].\n'
        for claim in ('1 is the first value.','9 is the last element.',
                      '3 is the middle element.','5 (absent)'):
            self.assertEqual(explanation_findings(text+claim),[])
        for claim in ('9 is the first element.','1 is the last value.','3 (absent)'):
            self.assertTrue(explanation_findings(text+claim))
        for number in (2,3):
            self.assertEqual(explanation_findings(f'The list [1,2,3,4].\n{number} is the middle element.'),[])
        self.assertEqual(explanation_findings('The sorted list [1,3,5,7].\nThe middle value is 4.'),[])
        self.assertEqual(explanation_findings('The list [3,1,2].\nThe middle value is 2.'),[])

    def test_negative_and_decimal_values_are_compared_without_eval(self):
        self.assertEqual(explanation_findings('The list [-2,-0.5,4].\n-0.5 is the middle element.'),[])
        self.assertTrue(explanation_findings('The list [-2,-0.5,4].\n4 is the middle element.'))

    def test_quoted_mistakes_code_and_ambiguous_data_are_not_assertions(self):
        for text in ('The targets [2,23,50,7] (first,middle,last,absent).',
                     'The list [2,5,16,23,50].\n> 23 is the middle element.',
                     'The list [2,5,16,23,50].\nThe statement "23 is the middle element" is incorrect.',
                     'The list [1,2,3].\n```python\n23 is the middle element\n```',
                     'The first array [1,2,3]. The second array [2,23,50].\n23 is the middle element.',
                     'The list [1,2,3].\nNever say 23 is the middle element.',
                     'Evidence [2] supports the result. 23 is the middle element.'):
            with self.subTest(text=text):
                self.assertEqual(explanation_findings(text),[])

    def test_qualified_comparison_and_unknown_table_types_are_left_to_reviewer(self):
        table='| Target | Linear comparisons | Binary probes |\n|---|---|---|\n|2|1|3|\n'
        for sentence in ('For target 23, the results show binary search uses fewer comparisons than linear search.',
                         'The results show binary search usually uses fewer comparisons than linear search.',
                         'Binary search has logarithmic worst-case complexity.',
                         'The results confirm that binary search uses fewer comparisons than linear search, but linear uses fewer for target 2.'):
            self.assertEqual(explanation_findings(table+'\n'+sentence),[])
        bad='The results confirm that binary search uses fewer comparisons than linear search.'
        self.assertEqual(explanation_findings(table+'\n'+bad)[0]['rule'],'comparison_counterexample')
        self.assertEqual(explanation_findings(table+'\n'+table+'\n'+bad),[])

    def test_dynamic_or_oversized_lists_are_not_evaluated(self):
        for values in ('[danger()]','[x for x in values]','[[1,2],[3,4]]',str(list(range(65)))):
            self.assertEqual(explanation_findings('The list '+values+'.\n23 is the middle element.'),[])
