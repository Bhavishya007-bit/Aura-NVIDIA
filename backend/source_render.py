"""Isolated PDF rendering worker; keeps MuPDF out of concurrent API threads."""
import json
import sys
import pymupdf


def main() -> int:
    mode, filename = sys.argv[1:3]
    try:
        with pymupdf.open(filename) as document:
            if document.needs_pass:
                raise ValueError("protected")
            if mode == "info":
                print(json.dumps({"page_count": document.page_count}))
                return 0
            position = int(sys.argv[3])
            if not 1 <= position <= document.page_count:
                raise ValueError("out_of_range")
            page = document[position - 1]
            area = max(1, page.rect.width * page.rect.height)
            scale = min(1.7, (8_000_000 / area) ** 0.5)
            pixels = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            sys.stdout.buffer.write(pixels.tobytes("png"))
            return 0
    except Exception as error:
        code = str(error) if isinstance(error, ValueError) else "render_failed"
        sys.stderr.write(json.dumps({"error": code}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
