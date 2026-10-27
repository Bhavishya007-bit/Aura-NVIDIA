# Uploads and study generation are independent

The application enforces a 100 MiB per-file limit in both frontend and backend. An oversized video must be compressed, split into shorter clips, or supplied as a transcript. Retrying unchanged bytes cannot resolve that validation failure. The upload batch UI now only offers retry when at least one failure is potentially retryable; mixed batches continue to allow valid files.

MP4 visual sampling calls the image OCR/vision reader, which previously overwrote video-wide progress with “Reading your image”. Nested frame calls now preserve the video progress callback. Existing saved MP4 jobs with the older stage are labelled “Reading a video frame”. This fixes the label; it does not prove a slow vision model is working or complete.

A study-generation failure for a selected DOCX is separate from an oversized or processing MP4. A screenshot of the generic generation banner cannot identify a model connection, verification, or source preparation failure. Reproduce one Generate attempt with the selected document ready, then inspect the corresponding backend terminal output. For the Docker build:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml logs --tail=100 app
```

Share the warning/error lines around that attempt, without `.env` contents or API keys. Native users should copy the corresponding Uvicorn terminal warnings instead. Source verification should not be disabled just to hide a generation failure.

Validation: production frontend build, 90 existing frontend tests, three upload/label regression tests, Python syntax compilation and a progress-callback suppression/restoration check passed. Live generation for the teammate's document still requires their logs and material context.

## DOCX study-item citation fix

The v2 study-item citation contract previously required a slide, page or timestamp even for Word passages, although DOCX extraction preserves paragraphs and does not invent page numbers. This could reject otherwise valid flashcards/assessment items.

Word evidence with no physical location now explicitly uses `document_excerpt: true` in the internal generated-item citation schema. Verification still requires the actual material and passage IDs, checks that the stored source is DOCX, and rejects this flag for page/slide/timestamp evidence or another file type. Existing citations retain their prior fields; the optional flag defaults to false. Public citation labels say “Document excerpt”. No database migration or fabricated Word page number is introduced.

Ten local checks covering Word excerpt identity, wrong-source rejection, mixed-location rejection and existing scoring passed. This addresses a confirmed DOCX-specific validation bug, but the teammate's particular document still needs a live Generate attempt; other provider or extraction failures require logs.
