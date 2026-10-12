import io
from pptx import Presentation
from .ocr import extract_image_text
from .utils import generate_unit_id, has_zip_signature
from .ppt_convert import convert_ppt_to_pptx, PptConversionError


def _shapes(shapes):
    for shape in shapes:
        children = getattr(shape, 'shapes', None)
        if children is not None:
            yield from _shapes(children)
        else:
            yield shape


def ingest_pptx(data: bytes, filename: str) -> tuple[list[dict], list[str]]:
    if filename.lower().endswith('.ppt'):
        try:
            data = convert_ppt_to_pptx(data)
        except (PptConversionError, ValueError) as error:
            print(f"[PPT] Conversion failed: {error}", flush=True)
            return [], [str(error)]
    if not has_zip_signature(data):
        return [], ['File does not have a valid Office ZIP signature.']
    try:
        presentation = Presentation(io.BytesIO(data))
    except Exception as error:
        return [], [f'Failed to open PPTX: {error}']
    units, warnings = [], []
    for slide_number, slide in enumerate(presentation.slides, start=1):
        text_parts, images = [], []
        for shape in _shapes(slide.shapes):
            if getattr(shape, 'has_table', False):
                text_parts.extend(' | '.join(cell.text.strip() for cell in row.cells) for row in shape.table.rows)
            elif getattr(shape, 'has_text_frame', False):
                text = shape.text.strip()
                if text:
                    text_parts.append(text.replace('\v', '\n'))
            try:
                image = getattr(shape, 'image', None)
                if image is not None:
                    images.append((image.blob, shape))
            except Exception as error:
                warnings.append(f'Slide {slide_number}: image extraction failed ({type(error).__name__}).')
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None else ''
        source = {'filename': filename, 'file_type': 'pptx'}
        native = '\n\n'.join(part for part in text_parts if part.strip()).strip()
        if native:
            units.append({'unit_id': generate_unit_id(filename, 'slide', str(slide_number)),
                          'source': source, 'text': native,
                          'source_location': {'kind': 'slide', 'slide_number': slide_number},
                          'extraction_status': 'extracted', 'warnings': []})
        before = len(units)
        for image_number, (blob, shape) in enumerate(images, start=1):
            text, metadata, image_warnings = extract_image_text(blob)
            warnings.extend(f'Slide {slide_number}, image {image_number}: {warning}' for warning in image_warnings)
            if not text:
                continue
            location = {'kind': 'slide', 'slide_number': slide_number, 'image_number': image_number,
                        'image_bbox_emu': {'left': int(shape.left), 'top': int(shape.top),
                                           'width': int(shape.width), 'height': int(shape.height)}, **metadata}
            units.append({'unit_id': generate_unit_id(filename, 'slide_image', f'{slide_number}-{image_number}'),
                          'source': source,
                          'text': f'Slide {slide_number}: {title}\nImage {image_number} recognized text (OCR; diagram relationships are not inferred):\n{text}',
                          'source_location': location, 'extraction_status': 'ocr', 'warnings': image_warnings})
        if not native and len(units) == before:
            warnings.append(f'Slide {slide_number} contains no recognized text.')
    return units, list(dict.fromkeys(warnings))
