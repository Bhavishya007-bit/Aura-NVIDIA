# Image materials and English tutoring

JPEG/JPG and PNG files can be selected in either upload control, including a
batch of up to five files. Each image becomes an owned source with page 1 as its
single internal location. The UI labels that location **Image**, opens the
original image, offers its download, and supports Explain this figure.

Actual file decoding verifies JPEG/PNG format, with a 20 megapixel limit before
loading image pixels and the existing 100 MiB file limit. Previews are normalized
to bounded PNGs. Renaming an unrelated file to .png does not make it supported.
Animated PNG uses the initial image only. GIF, SVG and unrestricted image URLs
are not added by this update.

OCR text is indexed with extraction metadata and the original image location.
When OLLAMA_VISION_MODEL is configured, ingestion also attempts a visual
interpretation, then checks it against the same image. Accepted interpretation
text is marked model-generated and not independently fact verified. A vision
failure retains readable OCR content. Text-free photographs/diagrams may need
vision configuration and a retry before there is usable searchable material.
Image intake can take longer because it calls the local vision model twice.

The prior Chinese-text screenshot is an extractive fallback, not a polished
tutor explanation. The characters appear in copied indexed quotations. That
does not prove they are visible on the original slide: extraction can include
hidden text or OCR errors. This update preserves original text for inspection
instead of deleting or translating source content without verification.

English questions receive English generated answers. Unrequested CJK script
fails answer validation; English fallbacks omit whole multilingual sentences
instead of deleting characters inside quotations. Explicit requested languages
remain possible. Only the selected source is used; topic checks and citation
grounding remain enabled. Supported English facts are selected into a bounded
context, with concise connected teaching prompts rather than many unrelated
examples and instructions. The intent checker also receives the selected file
name so a request to explain that file is not judged without its reference.

If full generation fails, a compact explanation is attempted over intact source
facts. It must pass the same language, citation, question and grounding checks.
If that also fails, a short labelled evidence fallback remains; no fabricated
explanation is substituted. This improves implementation behavior but is not a
claim of measured local-model accuracy. The tiny local text model can still
misunderstand, and model source checks can themselves err.

## Live validation

1. Upload a clear PNG/JPEG containing educational text or a labelled diagram.
2. Wait for preparation. Ask what the selected image shows, click Image and
   compare the original with Explain this figure's observations.
3. Ask a NEW English question about the cytoskeleton presentation. Expect an
   English explanation or a short evidence notice, without copied Chinese text.
4. Compare every factual statement with its citation, including directions and
   distinctions between related mechanisms. Do not treat a model check as proof.
5. Confirm response pipeline_version is aura-image-english-tutor-v5. If output
   still fails, retain that new /chat JSON so the specific case can be reproduced.

The README now describes image formats, setup, language handling, original-image
navigation and limitations. Existing database, GPU/CPU settings, uploads, quizzes,
mastery data, multi-file upload controls and source ownership checks are retained.
