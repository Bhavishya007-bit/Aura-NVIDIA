"""Notes recovery and safe diagnostics using controlled outputs, not live models."""
import unittest
from unittest.mock import patch
from pydantic import ValidationError
import httpx
from backend.study_v2 import notes
from backend.study_v2.contracts import StudyRequest

class NotesRecovery(unittest.IsolatedAsyncioTestCase):
    async def generate(self,docx=False,retry=False):
        request=StudyRequest(course_id=3,source_id=7,kind='notes')
        section={'id':'section-1','title':'Photosynthesis','chunk_ids':[1]}
        data={'sections':[section]}
        chunk={'source_id':7,'source_name':'Study.docx' if docx else 'Study.pdf','chunk_id':1,'content':'Plants use light to make sugars.','slide':None,'page':None if docx else 1,'seconds':None}
        calls=[]
        async def model(context,instructions,kind):
            if kind=='assessment':return {'supported':True}
            calls.append(instructions)
            self.assertEqual(instructions['evidence'][0]['document_excerpt'],docx)
            if retry and len(calls)==1:raise httpx.ConnectError('PRIVATE KEY AND DOCUMENT MUST NOT APPEAR')
            return {'id':'section-1','title':'Photosynthesis','text':'Plants use light to make sugars, as described in this source.','citations':[{'material_id':7,'chunk_id':1,**({'document_excerpt':True} if docx else {'page':1})}]}
        def persist(request,items,chunks,notices,*args): return {'items':list(items),'notices':list(notices)}
        with patch.object(notes,'outline',return_value=(data,[chunk])),patch.object(notes,'complete',side_effect=model),patch.object(notes,'persist',side_effect=persist),patch.object(notes,'guard'):
            if retry:
                with self.assertLogs(notes.log,level='WARNING') as logs:result=await notes.generate_notes(request,42)
                self.assertIn('ConnectError',' '.join(logs.output))
                self.assertNotIn('PRIVATE',' '.join(logs.output))
            else:result=await notes.generate_notes(request,42)
        self.assertEqual(len(result['items']),1)
        return calls
    async def test_pdf_notes_pass_source_check(self):await self.generate()
    async def test_docx_notes_use_locationless_excerpt(self):await self.generate(docx=True)
    async def test_transient_failure_is_logged_safely_and_retried(self):
        self.assertEqual(len(await self.generate(retry=True)),2)
    def test_schema_diagnostics_do_not_log_input_or_exception_message(self):
        try:notes.NoteSection.model_validate({'text':'PRIVATE SOURCE'})
        except ValidationError as error:
            details=notes.failure_details(error)
            self.assertTrue(details['schema_fields'])
            self.assertNotIn('PRIVATE',str(details))
    def test_provider_status_and_validation_reason_are_categorized(self):
        error=httpx.HTTPStatusError('PRIVATE RESPONSE',request=httpx.Request('POST','https://example.test'),response=httpx.Response(403))
        self.assertEqual(notes.failure_details(error)['http_status'],403)
        self.assertEqual(notes.failure_details(notes.NoteCheckError('source_check'))['reason'],'source_check')

if __name__=='__main__':unittest.main()
