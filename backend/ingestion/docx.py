"""Read Word material in order, preserving table relationships and images."""
import io
import hashlib
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from .utils import generate_unit_id, has_zip_signature
from .image import ingest_image


def ingest_docx(data: bytes, filename: str) -> tuple[list[dict], list[str]]:
    if not has_zip_signature(data):
        return [], ['File does not have a valid Office ZIP signature.']
    try:
        document = Document(io.BytesIO(data))
    except Exception as error:
        return [], [f'Failed to open DOCX: {error}']
    units, warnings = [], []
    source = {'filename': filename, 'file_type': 'docx'}
    paragraphs, first, paragraph_number = [], 1, 0

    def append(text, kind, number, location):
        if text.strip():
            units.append({'unit_id': generate_unit_id(filename, kind, str(number)),
                'source': source, 'text': text.strip(), 'source_location': location,
                'extraction_status': 'extracted', 'warnings': []})

    def flush():
        nonlocal paragraphs, first
        if paragraphs:
            append('\n'.join(paragraphs), 'paragraphs', first,
                {'kind': 'paragraph', 'paragraph_number': first,
                 'paragraph_end': paragraph_number})
            paragraphs = []

    for block_number, block in enumerate(document.iter_inner_content(), 1):
        if isinstance(block, Paragraph):
            paragraph_number += 1
            text = block.text.strip()
            if not text:
                continue
            if paragraphs and sum(len(t) for t in paragraphs) + len(text) > 1400:
                flush()
            if not paragraphs:
                first = paragraph_number
            paragraphs.append(text)
        elif isinstance(block, Table):
            flush()
            rows = [' | '.join(cell.text.strip().replace('\n', '; ') for cell in row.cells)
                    for row in block.rows]
            rows = [row for row in rows if row.replace('|', '').strip()]
            if not rows:
                continue
            # Repeat the first row as context with subsequent rows; isolated
            # cells lose which quantity/type a value describes.
            header = rows[0]
            append(header, 'table_header', block_number,
                   {'kind': 'table_row', 'table_number': block_number, 'row_number': 1})
            for row_number, row in enumerate(rows[1:], 2):
                append(header + '\n' + row, 'table_row', f'{block_number}-{row_number}',
                    {'kind': 'table_row', 'table_number': block_number, 'row_number': row_number})
    flush()
    seen_text, seen_images = set(), set()
    parts = [document.part]
    for section in document.sections:
        for area in [section.header, section.footer]:
            parts.append(area.part)
            text = '\n'.join(p.text.strip() for p in area.paragraphs if p.text.strip())
            if text and text not in seen_text:
                seen_text.add(text)
                append(text, 'header_footer', len(seen_text), {'kind': 'document_header_footer'})
    for part in parts:
        for relation in part.rels.values():
            if relation.is_external or not relation.reltype.endswith('/image'):
                continue
            blob = relation.target_part.blob
            digest = hashlib.sha256(blob).hexdigest()
            if digest in seen_images:
                continue
            seen_images.add(digest)
            number = len(seen_images)
            try:
                extracted, notices = ingest_image(blob, f'{filename}-image-{number}.png')
                warnings.extend(f'Document image {number}: {notice}' for notice in notices)
                for unit in extracted:
                    unit['source'] = source
                    unit['unit_id'] = generate_unit_id(filename, 'document_image', f'{number}-{unit["extraction_status"]}')
                    unit['source_location'] = {'kind': 'document_image', 'image_number': number,
                        'visual_interpretation': unit['extraction_status'] == 'vision_model_checked'}
                    units.append(unit)
            except ValueError:
                warnings.append(f'Document image {number}: embedded format is not JPEG/PNG; export as PDF to read it.')
    if not units:
        warnings.append('DOCX contains no extracted text or readable images. Check vision/OCR configuration or export as PDF.')
    return units, list(dict.fromkeys(warnings))
