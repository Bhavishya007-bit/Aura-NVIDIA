# Tutor evidence and expansion

The source section and outside explanation have different evidence status.
The UI displays a mixed-answer label when both are present. Source links refer
only to the cited source section. API citation_validation.valid remains false
for mixed answers; source_validation carries the source-section result.

Exact term matching and nearby slide/page retrieval supplement embedding
retrieval within the authenticated student's selected source and course.
Supporting excerpts are literal extracted text, not independently validated OCR.
If a paraphrase cannot be verified, relevant quotes can still be shown. A
question-relevance check prevents unrelated excerpts from being used as an
answer. If no relevant evidence exists, any accepted background is labelled
general background and carries no uploaded-source citations.

Additional explanations are generated and checked in separate model calls.
The same configured model checks topic consistency and contradiction against
the source anchors. It can make mistakes in both calls. It is not an external
fact checker, and no factual accuracy or expansion percentage is guaranteed.
Explicit source-only requests disable background; concise requests suppress
expansion. If checking fails, the supported source section remains available.

## Live checks after installation

1. In the selected cytoskeleton deck, ask "What is treadmilling? How does it
   work in humans?" The source section should cite relevant filament turnover
   text. Additional explanation, when accepted, should stay about filament
   dynamics and appropriate cell-level applications.
2. Ask the same question with "Use only the presentation." Expect source-backed
   text or relevant excerpts without added background.
3. Ask "Explain treadmilling in 2–3 sentences." Expect a concise source answer.
4. Switch to another standalone topic. The requested topic must not be rewritten
   into cytoskeleton merely because it appeared in the previous conversation.
5. Click a citation and confirm the original slide opens. Check that the login
   heading and cited-source buttons retain the previous display fixes.

Controlled checks cover source-first retrieval integration, ownership-filtered
keyword and neighboring-slide queries, failed paraphrase recovery, topic
relevance, rejected contradictory/uncertain supplements, source-only requests
and response metadata. The actual local Ollama model, PostgreSQL data and
uploaded presentation require the live checks above. Existing assessment and
adaptive-learning data are preserved; no migration or reindex is required.
