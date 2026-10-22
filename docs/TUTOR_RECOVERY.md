# Follow-up and slide-evidence recovery

This patch addresses two reported failures: a follow-up such as “Where is she
from?” losing the person named in the preceding answer, and “Explain membrane
proteins” receiving only background despite a relevant slide.

## Confirmed causes and changes

- Both chat screens filtered background assistant answers out of request history.
  They now send the last eight turns within the existing workspace/material scope.
  History identifies conversational subjects; it is never uploaded evidence.
- The reference resolver omitted person pronouns. It now handles she/her/he/him/
  his/they. Generation receives bounded context even if standalone rewriting fails.
- Lexical retrieval ranked long passages above short headings and fetched at most
  four anchors. It now ranks matching topic terms first, deduplicates before the
  limit, supports singular/plural and Greek label forms, and fetches same-slide
  labels with account, course and source restrictions intact.
- A full first-pass candidate list could discard evidence discovered on retry.
  Retry candidates now get space; failure of a second check cannot erase a
  previously checked partial answer. Lexical lookup survives embedding failure.
- Exact topic headings/labels prevent an absence claim even if the coverage judge
  rejects them. Aura shows a cited, exact excerpt and says explanatory coverage
  is uncertain. It does **not** infer mechanisms from labels or call a heading a
  fully supported answer.
- PPTX preparation now reads rendered slides as well as native text and embedded
  pictures. This covers visible SmartArt/vector labels when LibreOffice can
  render them. Hidden slides are included and page-count mismatches disable the
  rendered pass to prevent shifted citations. Rendered PDFs use bounded 240-DPI
  OCR, and picture text retains its slide context.
- Existing optional Ollama vision now uses `OLLAMA_BASE_URL`, not the Nebius
  text endpoint. When `OLLAMA_VISION_MODEL` is configured, rendered slides with
  graphics also receive model-checked interpretation, explicitly labeled as
  interpretation with limitations. No hosted vision model is automatically chosen.
- Preparation warnings remain visible after a job becomes ready and are saved
  with newly uploaded sources. An incomplete reading cannot establish absence.

## Apply locally

Stop the backend, then run from the project root:

```powershell
git pull --ff-only origin main
python -m uvicorn backend.main:app --reload
```

Restart the frontend development server or rebuild the frontend if serving a
production build. **Upload the presentation again and select the new upload.**
Existing database chunks are not automatically rewritten. Retrying embeddings
alone does not re-extract images. Existing materials and chat history are preserved.

Whole-slide rendering requires local LibreOffice (the same dependency used by
slide previews). `LIBREOFFICE_PATH` can point to `soffice.exe` on Windows. When
rendering is unavailable, native text/embedded OCR continue, but a reading notice
explains the limitation. Exporting the complete deck to PDF is another option.

OCR reads text, not the complete meaning of a picture. Optional vision requires
an installed, image-capable Ollama model and may be slow on a laptop. Its checking
is model-based, not independent proof. A label-only slide should receive a limited
sourced answer with separately identified additional explanation, not fabricated
diagram relationships.

## Verification

```powershell
python -m unittest evaluation.check_phase2 evaluation.check_tutor_recovery -v
$env:AURA_REAL_OCR_TESTS="1"
python -m unittest evaluation.check_phase2 evaluation.check_tutor_recovery -v
npm run build
```

45 checks pass with real OCR enabled, including a synthetic PPTX with a native
heading, an embedded membrane-protein picture, grouped text and a PDF export.
They verify label recovery and source position. The real-image tests require
LibreOffice and the OCR dependencies from `requirements.txt`; two are skipped
without `AURA_REAL_OCR_TESTS=1`. Model responses in orchestration tests are controlled
fixtures, not live Nemotron benchmarks.

The changed lexical SQL was also executed against a temporary PostgreSQL engine
(PGlite), checking heading rank, same-slide label retrieval, singular/plural/Greek
queries and exclusion of another owner's/source's/course's content. No user
database or hosted model was accessed. Frontend production build passes; the two
pre-existing missing decorative SVG warnings remain.

The reported original presentation has not been provided in this workspace.
Its exact membrane-protein slide and real model responses still need verification
after fresh preparation. No claim of zero false negatives is justified.

Technical references: [python-pptx shape types](https://python-pptx.readthedocs.io/en/latest/user/understanding-shapes.html),
[PyMuPDF page rendering](https://pymupdf.readthedocs.io/en/latest/recipes-images.html).
