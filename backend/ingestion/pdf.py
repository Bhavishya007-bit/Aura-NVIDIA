from backend.preparation_progress import report
import pymupdf
from .ocr import extract_images_text
from .page_batch import page_ocr_batches
from .page_render import render_for_ocr
from .utils import generate_unit_id, has_pdf_signature


def ingest_pdf(data: bytes, filename: str) -> tuple[list[dict], list[str]]:
    if not has_pdf_signature(data):
        return [], ['File does not have a valid PDF signature.']
    try:
        document = pymupdf.open(stream=data, filetype='pdf')
    except Exception as error:
        return [], [f'Failed to open PDF: {error}']
    units, warnings = [], []
    try:
        report("reading_pages", 0, len(document))
        for index, page, native_text, image, recognition, reading_error in page_ocr_batches(document, render_for_ocr, extract_images_text):
            number = index + 1
            source = {'filename': filename, 'file_type': 'pdf'}
            before = len(units)
            try:
                text = native_text.strip()
                if text:
                    units.append({'unit_id': generate_unit_id(filename, 'page', str(number)),
                                  'source': source, 'text': text,
                                  'source_location': {'kind': 'page', 'page_number': number},
                                  'extraction_status': 'extracted', 'warnings': []})
                if reading_error is not None:
                    raise reading_error
                if recognition is not None:
                    ocr_text, metadata, ocr_warnings = recognition
                    warnings.extend(f'Page {number}: {warning}' for warning in ocr_warnings)
                    if ocr_text:
                        units.append({'unit_id': generate_unit_id(filename, 'page_ocr', str(number)),
                                      'source': source,
                                      'text': f'Page {number} recognized text (OCR; diagram relationships are not inferred):\n{ocr_text}',
                                      'source_location': {'kind': 'page', 'page_number': number, **metadata},
                                      'extraction_status': 'ocr', 'warnings': ocr_warnings})
            except Exception as error:
                warnings.append(f'Page {number}: extraction failed ({type(error).__name__}).')
            if len(units) == before:
                warnings.append(f'Page {number} contains no recognized text.')
            report("reading_pages", number, len(document))
    finally:
        document.close()
    return units, list(dict.fromkeys(warnings))

