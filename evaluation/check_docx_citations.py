"""Word citations retain source identity without invented page numbers."""
import unittest
from pydantic import ValidationError
from backend.study_v2.contracts import Card, Citation, verified_citations

class DocxCitationChecks(unittest.TestCase):
    def card(self, **changes):
        ref = dict(material_id=7, chunk_id=11, document_excerpt=True)
        ref.update(changes)
        return Card(id='word-card', card_type='question_answer', question='What is evaporation?', answer='Liquid water changes into water vapour.', topic='Water cycle', citations=[ref])

    def test_docx_excerpt_accepts_actual_material_and_passage(self):
        item=self.card()
        self.assertTrue(verified_citations(item,[dict(chunk_id=11,source_id=7,source_name='Water cycle.DOCX',page=None,slide=None,seconds=None)]))

    def test_excerpt_cannot_bypass_physical_or_source_identity(self):
        for change in [dict(source_name='notes.pdf'),dict(source_id=8),dict(page=1),dict(slide=2),dict(seconds=0)]:
            evidence=dict(chunk_id=11,source_id=7,source_name='notes.docx',page=None,slide=None,seconds=None)
            evidence.update(change)
            with self.subTest(change=change):self.assertFalse(verified_citations(self.card(),[evidence]))
        self.assertFalse(verified_citations(self.card(),[]))

    def test_excerpt_and_physical_location_cannot_be_mixed(self):
        with self.assertRaises(ValidationError):self.card(page=1)
        with self.assertRaises(ValidationError):Citation(material_id=7,chunk_id=11)

    def test_existing_pdf_card_still_requires_correct_page(self):
        item=self.card(document_excerpt=False,page=2)
        self.assertTrue(verified_citations(item,[dict(chunk_id=11,source_id=7,page=2)]))
        self.assertFalse(verified_citations(item,[dict(chunk_id=11,source_id=7,page=3)]))

if __name__=='__main__':unittest.main()
