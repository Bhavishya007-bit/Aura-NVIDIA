"""Readable OCR page renders with bounded memory, including vector labels."""
import math


def render_for_ocr(page):
    area = max(1, page.rect.width * page.rect.height)
    dpi = max(1, min(240, int(72 * math.sqrt(12_000_000 / area))))
    return page.get_pixmap(dpi=dpi, alpha=False).tobytes('png')
