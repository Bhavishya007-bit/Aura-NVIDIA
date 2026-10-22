"""Run the long-document query in PostgreSQL and exercise its real selector."""
import json
import os
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch


NODE_QUERY = r'''
const {PGlite}=require(process.env.AURA_PGLITE_MODULE);
const fs=require('node:fs');
(async()=>{
 const q=JSON.parse(fs.readFileSync(0,'utf8'));const db=new PGlite();
 await db.exec(`CREATE TABLE courses(course_id int,owner_student_id int);
 CREATE TABLE sources(source_id int,course_id int,owner_student_id int,source_name text,source_type text);
 CREATE TABLE topics(topic_id int,topic_name text);
 CREATE TABLE chunks(chunk_id int,source_id int,content text,page_number int,slide_number int,timestamp_seconds real,timestamp_end real,topic_id int,metadata jsonb);
 INSERT INTO courses VALUES(3,42),(4,43),(5,42);
 INSERT INTO sources VALUES(7,3,42,'synthetic.pptx','pptx'),(8,4,43,'private.pptx','pptx'),(9,5,42,'other-course.pptx','pptx');`);
 const rows=q.fixture_rows || Array.from({length:39},(_,i)=>i+1).flatMap(n=>[
  [n*2,7,`Slide ${n} defines a native teaching point about membrane structure, proteins, transport and cellular boundaries.`,null,n,null,null,null,{extraction_status:'extracted'}],
  [n*2+1,7,`OCR slide ${n} `+'noisy screenshot menus '.repeat(80),null,n,null,null,null,{extraction_status:'ocr'}]
 ]);
 for(const r of rows){await db.query('INSERT INTO chunks VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9)',r);}
 await db.query('INSERT INTO chunks VALUES(999,8,$1,null,40,null,null,null,null)',['Private content excluded']);
 await db.query('INSERT INTO chunks VALUES(1000,9,$1,null,41,null,null,null,null)',['Other course excluded']);
 const data=(await db.query(q.sql,q.params)).rows;
 console.log(JSON.stringify(data.map(r=>[r.chunk_id,r.source_id,r.source_name,r.source_type,r.content,r.page_number,r.slide_number,r.timestamp_seconds,r.timestamp_end,r.topic_name,r['?column?']])));
 await db.close();
})().catch(e=>{console.error(e);process.exitCode=1});
'''


def query_document(limit=96, fixture_rows=None):
    encoder = types.ModuleType('backend.ai.embeddings')
    encoder.EmbeddingModel = object
    encoder.LEGACY_MODEL = 'Qwen/Qwen3-Embedding-0.6B'
    encoder.get_embedding_model = Mock(side_effect=AssertionError('Document reads must not load an encoder'))
    with patch.dict(sys.modules, {'backend.ai.embeddings': encoder}):
        from backend.ai.pg_retrieval import PostgresRetriever
    cursor = Mock()
    cursor.__enter__, cursor.__exit__ = Mock(return_value=cursor), Mock(return_value=False)
    def execute(sql, params):
        for i in range(len(params)):
            sql = sql.replace('%s', f'${i + 1}', 1)
        payload = {'sql': sql, 'params': params}
        if fixture_rows is not None:
            payload['fixture_rows'] = fixture_rows
        result = subprocess.run(['node', '-e', NODE_QUERY], input=json.dumps(payload),
            text=True, capture_output=True, check=True, timeout=45)
        cursor.fetchall.return_value = json.loads(result.stdout)
    cursor.execute.side_effect = execute
    connection = Mock(); connection.cursor.return_value = cursor
    retriever = PostgresRetriever(); retriever._get_connection = Mock(return_value=connection)
    result = retriever.document_context(course_id=3, source_id=7, owner_student_id=42, limit=limit)
    connection.close.assert_called_once()
    return result


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'), 'Optional PostgreSQL engine not configured')
class DocumentContextChecks(unittest.TestCase):
    def test_all_39_locations_survive_and_native_text_precedes_noisy_ocr(self):
        result = query_document()
        self.assertEqual(result['scope'], 'all_available_locations')
        self.assertEqual(result['locations_selected'], 39)
        self.assertEqual({r.chunk.slide for r in result['results'][:39]}, set(range(1,40)))
        self.assertTrue(all('native teaching' in r.chunk.content for r in result['results'][:39]))
        self.assertTrue(result['all_chunks_included'])

    def test_owner_course_and_source_scope(self):
        result = query_document()
        self.assertTrue(all(r.chunk.source_id == 7 for r in result['results']))
        self.assertNotIn('Private content', ' '.join(r.chunk.content for r in result['results']))

    def test_limited_context_does_not_claim_all_locations(self):
        result = query_document(12)
        self.assertEqual(result['scope'], 'sampled_locations')
        self.assertEqual(result['locations_selected'], 12)
        self.assertFalse(result['all_chunks_included'])


if __name__ == '__main__':
    unittest.main()
