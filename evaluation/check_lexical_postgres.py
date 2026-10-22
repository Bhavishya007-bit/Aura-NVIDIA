"""Execute real retriever SQL in an optional local PGlite PostgreSQL engine.

Set AURA_PGLITE_MODULE to an installed @electric-sql/pglite package directory.
No user database, embedding model or hosted API is used. Fixtures are synthetic.
"""
import json
import os
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch


NODE_CHECK = r'''
const {PGlite} = require(process.env.AURA_PGLITE_MODULE);
const fs = require('node:fs');
(async () => {
 const calls=JSON.parse(fs.readFileSync(0,'utf8'));
 const db=new PGlite();
 await db.exec(`
 CREATE TABLE courses(course_id int,owner_student_id int);
 CREATE TABLE sources(source_id int,course_id int,owner_student_id int,source_name text,source_type text);
 CREATE TABLE topics(topic_id int,topic_name text);
 CREATE TABLE chunks(chunk_id int,source_id int,content text,page_number int,slide_number int,timestamp_seconds real,timestamp_end real,topic_id int);
 INSERT INTO courses VALUES(3,42),(4,43),(5,42);
 INSERT INTO sources VALUES(7,3,42,'synthetic.pptx','pptx'),(8,4,43,'other-user.pptx','pptx'),(9,5,42,'other-course.pptx','pptx');
 INSERT INTO chunks VALUES
 (1,7,'Membrane integral proteins',null,16,null,null,null),
 (2,7,E'Membrane Proteins\nPeripheral proteins associate with the membrane surface. Integral proteins interact with its hydrophobic core.',null,9,null,null,null),
 (3,7,'Membrane proteins with β-barrel structure',null,18,null,null,null),
 (4,7,'Diagram labels: FepA, OmpLA, Maltoporin, TolC',null,18,null,null,null),
 (5,7,'Integral membrane proteins',null,10,null,null,null),
 (6,7,'Membrane proteins are examples.',null,12,null,null,null),
 (7,8,'Membrane proteins',null,1,null,null,null),
 (8,9,'Membrane proteins',null,1,null,null,null),
 (9,7,E'Apical\nMembrane\nprotein\nBasolateral',null,39,null,null,null);
 `);
 const anchors=(await db.query(calls[0].sql,calls[0].params)).rows;
 calls[1].params[4]=[];
 calls[1].params[5]=[...new Set(anchors.map(r=>r.slide_number))];
 const nearby=(await db.query(calls[1].sql,calls[1].params)).rows;
 console.log(JSON.stringify({anchors,nearby}));
 await db.close();
})().catch(e=>{console.error(e);process.exitCode=1});
'''


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'), 'Optional PostgreSQL engine not configured')
class LexicalPostgresChecks(unittest.TestCase):
    def query(self, question):
        # Isolate the unused neural runtime while executing the real SQL builder.
        encoder = types.ModuleType('backend.ai.embeddings')
        encoder.EmbeddingModel = object
        encoder.LEGACY_MODEL = 'Qwen/Qwen3-Embedding-0.6B'
        encoder.get_embedding_model = Mock(side_effect=AssertionError('No encoder expected'))
        with patch.dict(sys.modules, {'backend.ai.embeddings': encoder}):
            from backend.ai.pg_retrieval import PostgresRetriever
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        cursor.fetchall.side_effect = [[(2,7,'synthetic.pptx','pptx','Membrane Proteins',None,9,None,None,None)], []]
        connection = Mock()
        connection.cursor.return_value = cursor
        retriever = PostgresRetriever()
        retriever._get_connection = Mock(return_value=connection)
        retriever.concept_context(question, 3, 7, 42, limit=10)
        calls = []
        for call in cursor.execute.call_args_list:
            sql, params = call.args
            for index in range(len(params)):
                sql = sql.replace('%s', f'${index + 1}', 1)
            calls.append({'sql': sql, 'params': params})
        result = subprocess.run(['node', '-e', NODE_CHECK], input=json.dumps(calls),
            text=True, capture_output=True, check=True, timeout=45)
        return json.loads(result.stdout)

    def test_exact_heading_beats_shorter_incidental_mentions(self):
        for question in ('Explain membrane protein', 'Explain membrane proteins'):
            with self.subTest(question=question):
                result = self.query(question)
                self.assertEqual(result['anchors'][0]['slide_number'], 9)

    def test_beta_barrel_retrieves_same_slide_picture_labels(self):
        result = self.query('Explain beta barrel proteins')
        self.assertEqual(result['anchors'][0]['slide_number'], 18)
        self.assertTrue(any('Maltoporin' in row['content'] for row in result['nearby']))

    def test_owner_course_and_source_scope(self):
        result = self.query('Explain membrane proteins')
        self.assertTrue(all(row['source_id'] == 7 for row in result['anchors'] + result['nearby']))


if __name__ == '__main__':
    unittest.main()
