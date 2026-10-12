"""Local OCR for source images, with provenance and confidence retained."""
import hashlib
import logging
import os
from functools import lru_cache
from threading import Lock

_engine = None
_lock = Lock()
logger = logging.getLogger(__name__)


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR(text_score=0.55, intra_op_num_threads=2, inter_op_num_threads=1)
    return _engine


def _reading_rows(blocks: list[dict]) -> str:
    """Retain approximate left-to-right rows, rather than grouping columns."""
    rows = []
    for block in sorted(blocks, key=lambda item: (item['y'], item['x'])):
        tolerance = max(5, block['height'] * 0.5)
        if rows and abs(rows[-1][0] - block['y']) <= tolerance:
            rows[-1][1].append(block)
        else:
            rows.append((block['y'], [block]))
    return '\n'.join(' | '.join(item['text'] for item in sorted(row, key=lambda item: item['x']))
                     for _, row in rows)


@lru_cache(maxsize=64)
def _recognize(data: bytes) -> tuple[str, tuple, str | None]:
    if os.getenv('AURA_OCR_ENABLED', 'true').lower() in {'0', 'false', 'no'}:
        return '', (), 'Image OCR is disabled.'
    try:
        with _lock:
            result, _ = _get_engine()(data)
        blocks = []
        for box, text, score in result or []:
            text = str(text).strip()
            if not text or float(score) < 0.55:
                continue
            xs, ys = [float(point[0]) for point in box], [float(point[1]) for point in box]
            blocks.append({'text': text, 'confidence': round(float(score), 4),
                           'box': [[float(x), float(y)] for x, y in box],
                           'x': min(xs), 'y': (min(ys) + max(ys)) / 2,
                           'height': max(ys) - min(ys)})
        return _reading_rows(blocks), tuple(blocks), None
    except Exception as error:
        message = 'Image OCR unavailable. Install requirements-multimodal.txt and retry the upload.'
        logger.warning('%s (%s)', message, type(error).__name__)
        raise RuntimeError(message) from error


def extract_image_text(data: bytes) -> tuple[str, dict, list[str]]:
    try:
        text, blocks, warning = _recognize(data)
    except RuntimeError as error:
        return '', {}, [str(error)]
    provenance = {'ocr_engine': 'rapidocr-onnxruntime',
                  'image_sha256': hashlib.sha256(data).hexdigest(),
                  'ocr_blocks': list(blocks)}
    return text, provenance, [warning] if warning else []
