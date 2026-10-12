"""Bounded OCR concurrency, hash-based single-flight cache, source provenance."""
import hashlib
import logging
import os
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from threading import Lock, local

logger = logging.getLogger(__name__)
_cache = OrderedDict()
_pending = {}
_lock = Lock()
_local = local()
_workers = max(1, min(2, int(os.getenv('AURA_OCR_WORKERS', '2'))))
_executor = ThreadPoolExecutor(max_workers=_workers, thread_name_prefix='aura-ocr')

def _get_engine():
    if not hasattr(_local, 'engine'):
        from rapidocr_onnxruntime import RapidOCR
        _local.engine = RapidOCR(text_score=0.55, intra_op_num_threads=2, inter_op_num_threads=1)
    return _local.engine

def _reading_rows(blocks):
    rows = []
    for block in sorted(blocks, key=lambda item: (item['y'], item['x'])):
        tolerance = max(5, block['height'] * 0.5)
        if rows and abs(rows[-1][0] - block['y']) <= tolerance:
            rows[-1][1].append(block)
        else:
            rows.append((block['y'], [block]))
    return '\n'.join(' | '.join(item['text'] for item in sorted(row, key=lambda item: item['x']))
                     for _, row in rows)

def _recognize(data):
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
    return _reading_rows(blocks), blocks

def _cached_recognize(data, digest):
    with _lock:
        if digest in _cache:
            _cache.move_to_end(digest)
            return deepcopy(_cache[digest])
        future = _pending.get(digest)
        leader = future is None
        if leader:
            future = Future()
            _pending[digest] = future
    if not leader:
        return deepcopy(future.result())
    try:
        value = _recognize(data)
        with _lock:
            _cache[digest] = value
            while len(_cache) > 128:
                _cache.popitem(last=False)
        future.set_result(value)
        return deepcopy(value)
    except Exception as error:
        future.set_exception(error)
        raise
    finally:
        with _lock:
            _pending.pop(digest, None)

def extract_image_text(data: bytes):
    digest = hashlib.sha256(data).hexdigest()
    if os.getenv('AURA_OCR_ENABLED', 'true').lower() in {'0', 'false', 'no'}:
        return '', {}, ['Image OCR is disabled.']
    try:
        text, blocks = _cached_recognize(data, digest)
    except Exception as error:
        message = 'Image OCR unavailable. Install requirements.txt and retry the upload.'
        logger.warning('%s (%s)', message, type(error).__name__)
        return '', {}, [message]
    return text, {'ocr_engine': 'rapidocr-onnxruntime', 'image_sha256': digest,
                  'ocr_blocks': blocks}, []

def extract_images_text(images):
    """Preserve input order and reuse at most two long-lived OCR engines."""
    return list(_executor.map(extract_image_text, images))
