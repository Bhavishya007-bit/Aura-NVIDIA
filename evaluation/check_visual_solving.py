"""Replay schema-description refusals without live models or student material."""
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from PIL import Image, ImageDraw

from backend.figure_tools import image_tutor_answer, interpret_image
from backend.multi_image_tutor import images_tutor_answer
from backend.visual_tasks import requests_sql, sql_completion_feedback


# Authored test schema/query, not the student's unread screenshot or model code.
SCHEMA = '''matches(match_num PK, match_date, stadium_id FK -> stadiums.stadium_id)
match_referees(match_num FK -> matches.match_num,
               main_referee FK -> referees.referee_id,
               fourth_referee FK -> referees.referee_id)
referees(referee_id PK, referee_name)
stadiums(stadium_id PK, stadium_name)'''
QUESTION = ("Write an SQL statement to find the match number of the match held on "
            "'2020-05-15' and the name of the fourth referee. Print match_num first, "
            "followed by the fourth referee's name.")
QUERY = '''SELECT m.match_num, r.referee_name
FROM matches AS m
JOIN match_referees AS mr ON mr.match_num = m.match_num
JOIN referees AS r ON r.referee_id = mr.fourth_referee
WHERE m.match_date = '2020-05-15';'''


def solution():
    return {'answerable': True,
            'observations': ['matches has match_num and match_date.',
                'match_referees.match_num references matches.match_num.',
                'match_referees.fourth_referee references referees.referee_id.',
                'referees has referee_name.'],
            'explanation': '```sql\n' + QUERY + '\n```\n'
                'Join each match to its referee assignment, then use fourth_referee '
                'to get the fourth referee name. Filter the match date.',
            'limitations': []}


def refusal(answerable=True):
    return {'answerable': answerable,
            'observations': ['The schema contains matches, referees, match_referees and stadiums.'],
            'explanation': 'An SQL query would need to join the tables to find the match and fourth referee.',
            'limitations': ['The diagram does not provide the exact SQL query needed to answer the question, only the schema and relationships.']}


class VisualSolvingChecks(unittest.TestCase):
    def setUp(self):
        image = Image.new('RGB', (900, 240), 'white')
        ImageDraw.Draw(image).multiline_text((10, 10), SCHEMA, fill='black')
        output = io.BytesIO(); image.save(output, format='PNG')
        self.png = output.getvalue()
        self.reasoner = Mock()
        self.reasoner.for_task.return_value = self.reasoner
        self.reasoner.for_summary.return_value = self.reasoner
        self.reasoner.with_output_budget.return_value = self.reasoner
        self.reasoner.generate_json.return_value = {'answerable': True, 'query': QUERY,
            'explanation': 'Join through the fourth-referee key and filter the match date.', 'limitations': []}
        self.reasoner_patch = patch('backend.visual_sql.LLM', return_value=self.reasoner)
        self.reasoner_patch.start(); self.addCleanup(self.reasoner_patch.stop)

    def test_single_image_replays_reported_refusal_and_returns_query(self):
        for answerable in (True, False):
            readable = refusal(answerable); readable['observations'] = solution()['observations']
            with self.subTest(answerable=answerable), patch('backend.figure_tools.vision_json',
                    side_effect=[readable, {'supported': True}]) as model:
                result = interpret_image(self.png, QUESTION)
            self.assertEqual(model.call_count, 2)
            for call in model.call_args_list:
                self.assertEqual(call.args[0], self.png)
                self.assertIn(QUESTION, call.args[1])
            self.assertIn(QUERY, result['explanation'])
            self.assertEqual(result['limitations'], [])
            self.assertTrue(result['answerable'])
            self.assertFalse(result['independently_fact_verified'])

    def test_successful_derivation_is_reviewed_without_requiring_printed_solution(self):
        with patch('backend.figure_tools.vision_json', side_effect=[solution(), {'supported': True}]) as model:
            result = interpret_image(self.png, QUESTION)
        self.assertEqual(model.call_count, 2)
        self.assertIn('need not appear verbatim', model.call_args_list[1].args[1])
        self.assertIn(QUERY, result['explanation'])
        # Execute only the authored fixture query against a synthetic in-memory
        # fixture; production image tutoring never executes SQL/model output.
        with sqlite3.connect(':memory:') as db:
            db.executescript('''CREATE TABLE matches(match_num int, match_date text, stadium_id int);
                CREATE TABLE referees(referee_id int, referee_name text);
                CREATE TABLE match_referees(match_num int, main_referee int, fourth_referee int);
                CREATE TABLE stadiums(stadium_id int, stadium_name text);
                INSERT INTO matches VALUES(1,'2020-05-15',1),(2,'2020-05-16',1);
                INSERT INTO referees VALUES(10,'Main official'),(20,'Fourth official');
                INSERT INTO match_referees VALUES(1,10,20),(2,20,10);''')
            self.assertEqual(db.execute(QUERY).fetchall(), [(1, 'Fourth official')])

    def test_description_only_cannot_pass_as_a_completed_sql_answer(self):
        bad = refusal(); bad['limitations'] = []
        self.reasoner.generate_json.return_value = {'answerable': True, 'query': '',
            'explanation': 'You would need to join tables.', 'limitations': []}
        with patch('backend.figure_tools.vision_json', return_value=bad) as model:
            with self.assertRaises(HTTPException) as error:
                interpret_image(self.png, QUESTION)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(model.call_count, 1)
        self.assertEqual(self.reasoner.generate_json.call_count, 2)

    def test_genuine_unreadable_join_key_is_preserved_not_guessed(self):
        missing = {'answerable': False, 'observations': ['The referee key label is blurred.'],
            'explanation': 'Which referee column does fourth_referee reference? That key is unreadable.',
            'limitations': ['The referenced key label is unreadable.']}
        with patch('backend.figure_tools.vision_json', return_value=missing) as model:
            result = interpret_image(self.png, QUESTION)
        self.assertEqual(model.call_count, 1)
        self.assertFalse(result['answerable'])
        self.assertNotIn('SELECT', result['explanation'])
        self.reasoner.generate_json.assert_not_called()

    def test_a_query_with_misread_identifiers_is_withheld_when_review_rejects_it(self):
        bad = solution()
        bad['explanation'] = bad['explanation'].replace('mr.fourth_referee', 'mr.main_referee')
        self.reasoner.generate_json.return_value['query'] = QUERY.replace('mr.fourth_referee', 'mr.main_referee')
        with patch('backend.figure_tools.vision_json', side_effect=[bad, {'supported': False}]):
            result = interpret_image(self.png, QUESTION)
        self.assertFalse(result['answerable'])
        self.assertNotIn(QUERY, result['explanation'])

    def test_plain_query_output_questions_do_not_require_generating_new_sql(self):
        for question in ('What will be the output of the following query? SELECT name FROM teams;',
                         'Explain this SQL query.', 'Explain this SQL query to me.',
                         'Explain the SQL query for finding matches.', 'Show the SQL query output.',
                         'Describe the four tables and their relationships.'):
            with self.subTest(question=question):
                self.assertFalse(requests_sql(question))
                self.assertIsNone(sql_completion_feedback(question, refusal()))
        for question in (QUESTION, 'Give me the SQL query to find all teams.',
                         'SQL query for the fourth referee?', 'Write a statement in SQL to list matches.'):
            with self.subTest(question=question):
                self.assertTrue(requests_sql(question))
        good = solution(); good['limitations'] = ['No SQL query was executed.']
        self.assertIsNone(sql_completion_feedback(QUESTION, good))

    def test_chat_wrapper_preserves_sql_code_and_original_image_citation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'authored-schema.png'; path.write_bytes(self.png)
            with patch.dict('os.environ', {'OLLAMA_VISION_MODEL': 'fixture-vision'}), \
                 patch('backend.figure_tools.owned_original', return_value={'path': path, 'title': path.name}), \
                 patch('backend.figure_tools.vision_json', side_effect=[solution(), {'supported': True}]):
                result = image_tutor_answer(7, QUESTION, 42)
        self.assertIn('```sql\n' + QUERY + '\n```', result['answer'])
        self.assertTrue(result['answer'].endswith('[1]'))
        self.assertEqual(result['sources'][0]['source_id'], 7)
        self.assertFalse(result['citation_validation']['valid'])

    def test_multiple_images_repair_the_same_sql_failure_with_all_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / f'authored-schema-{n}.png' for n in (1, 2)]
            for path in paths: path.write_bytes(self.png)
            sources = [{'path': p, 'title': p.name} for p in paths]
            bad = refusal(False); bad['observations'] = [{'image': 1, 'text': SCHEMA}, {'image': 2, 'text': SCHEMA}]
            good = solution(); good['observations'] = bad['observations']
            with patch('backend.multi_image_tutor.owned_original', side_effect=sources), \
                 patch('backend.multi_image_tutor.vision_json', side_effect=[bad, {'supported': True}]) as model:
                result = images_tutor_answer([7, 8], QUESTION, 42)
            for call in model.call_args_list:
                self.assertEqual(len(call.args[0]), 2)
                self.assertIn(QUESTION, call.args[1])
            self.assertEqual(model.call_count, 2)
            self.assertIn(QUERY, result['answer'])
            self.assertEqual([source['source_id'] for source in result['sources']], [7, 8])
            self.assertTrue(result['answer'].endswith('[1][2]'))

    def test_multiple_images_do_not_publish_a_repeated_false_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'authored.png'; path.write_bytes(self.png)
            sources = [{'path': path, 'title': path.name}] * 2
            bad = refusal(False); bad['observations'] = []
            with patch('backend.multi_image_tutor.owned_original', side_effect=sources), \
                 patch('backend.multi_image_tutor.vision_json', return_value=bad) as model:
                with self.assertRaises(HTTPException) as error:
                    images_tutor_answer([7, 8], QUESTION, 42)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(model.call_count, 1)
