# Initial material ingestion component

This is a standalone Python extraction package. It does not change the React upload page, start an API, store files, or call an AI service. A future backend can pass its upload stream and original filename into `ingestion.ingest_file`.

## Install and test

From the project root, create a Python environment and install the extraction libraries:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-ingestion.txt
python -m unittest discover -s tests -v
```

The tests generate small PDF, PPTX, and DOCX examples in memory. They also cover blank/corrupt/missing/unsupported files, the 100 MiB limit, stable IDs, JSON serialization, and the no-provider MP4 result. No team dataset is read.

## Call the component

Pass a path, or a binary stream plus its original filename. For example, a future FastAPI route could call `ingest_file(upload.file, upload.filename)` after its own authentication and request-size handling. This package does not define that route or API contract.

```python
from ingestion import ingest_file

result = ingest_file("materials/chapter-4.pdf")
```

For framework upload objects, pass both the stream and client filename:

```python
result = ingest_file(upload.file, upload.filename)
```

## JSON output

The response is JSON-serializable and uses schema version `1.0`:

```json
{
  "schema_version": "1.0",
  "source": { "filename": "chapter-4.pdf", "file_type": "pdf" },
  "status": "success",
  "content_units": [
    {
      "unit_id": "cu_…",
      "source": { "filename": "chapter-4.pdf", "file_type": "pdf" },
      "text": "Extracted text from this page.",
      "source_location": { "kind": "page", "page_number": 1 },
      "extraction_status": "extracted",
      "warnings": []
    }
  ],
  "warnings": []
}
```

Each PDF page and PPTX slide produces one unit, including a `no_text` unit when the page/slide has no selectable text. DOCX produces one unit per non-empty body paragraph and records its original 1-based paragraph number; DOCX page numbers are not guessed. `unit_id` is deterministic from filename, format, location, and extracted text, so unchanged input at the same location produces the same identifier.

Top-level statuses are `success`, `partial`, `empty`, `unsupported`, `not_configured`, and `error`. PDF warnings may indicate pages with no text layer; OCR is not implemented. A document with a mixture of text and blank pages/slides is `partial`.

## Implemented and pending

- **Implemented:** PDF text extraction with PyMuPDF, PPTX slide text extraction with python-pptx, DOCX body paragraph extraction with python-docx, lightweight file-signature checks, stable content-unit IDs, a shared output shape, graceful unsupported/empty/corrupt/unreadable/oversize results, and a 100 MiB file-size guard. Signature checks are not malware scanning.
- **Video integration point only:** MP4 input reports whether `ffmpeg` is discoverable with `shutil.which`. A `VideoTranscriber` protocol accepts video bytes and returns timestamped segments. No transcription provider is selected or bundled. Without an injected provider the result is `not_configured`, has no content units, and explicitly says no transcript was created. FFmpeg was not available on PATH when this component was prepared.
- **Not included:** HTTP upload handling, background jobs, persistence, database/schema choices, OCR, video/audio decoding, transcription, embeddings, retrieval, topic labels, learner modeling, or quiz generation.

The Python size limit uses 100 MiB (104,857,600 bytes), matching the frontend's current `100 * 1024 * 1024` validation. Keep the limits aligned if either changes.
