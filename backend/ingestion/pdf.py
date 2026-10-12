import pymupdf
from .ocr import extract_image_text
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
        for index, page in enumerate(document):
            number = index + 1
            source = {'filename': filename, 'file_type': 'pdf'}
            before = len(units)
            try:
                text = page.get_text('text').strip()
                if text:
                    units.append({'unit_id': generate_unit_id(filename, 'page', str(number)),
                                  'source': source, 'text': text,
                                  'source_location': {'kind': 'page', 'page_number': number},
                                  'extraction_status': 'extracted', 'warnings': []})
                if not text or page.get_images() or page.get_drawings():
                    image = page.get_pixmap(dpi=150, alpha=False).tobytes('png')
                    ocr_text, metadata, ocr_warnings = extract_image_text(image)
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
    finally:
        document.close()
    return units, list(dict.fromkeys(warnings))
