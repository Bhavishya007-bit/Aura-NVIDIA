# Upload preparation performance

File preparation runs on the machine hosting Aura, not on the remote Nemotron model. The packaged Docker image uses CPU Qwen embeddings; moving from a CUDA-enabled native Python environment to this CPU image is not the same performance configuration. A rebuilt container also reloads its models on first use; downloads depend on the retained model volume and internet access. Queued files wait for the current preparation job. Optional vision interpretation can also dominate slide preparation time. Do not infer a specific cause from elapsed time alone.

## Changes

- The local Compose setup now defaults to four embedding CPU threads, bounded by the encoder's existing available-CPU check, instead of inheriting the generic image's conservative two-thread setting. Operators can set `AURA_EMBEDDING_THREADS` lower if their Docker VM has few CPUs. The base Docker dependency layers are unchanged.
- PDF and whole-slide OCR use windows of at most two rendered pages, dispatching image recognition through the existing two-worker OCR pool. PDF handles are only accessed from the rendering thread. Page order, native text, OCR evidence, images/diagrams, full-slide reading and optional vision remain enabled. No pages are sampled away.
- Embedding work groups missing texts by length inside existing batches to reduce padding. Results return in input order; duplicate/cache behavior is preserved. Qwen model, precision, dimensions and sequence limits are unchanged. This is not a smaller-model substitution or a GPU-enabled container.
- Preparation logs record stage transitions, completed-stage elapsed time and total processing time. The UI shows age after two minutes and distinguishes waiting from processing; it does not invent an ETA.

These changes target CPU and OCR overhead. Actual improvement depends on the file, local CPU/RAM, Docker resource allocation, model warm-up and optional vision calls. The seven offline checks include real PDF/PPT structures with controlled OCR, bounded windows, failure isolation and embedding order/cache checks. They are not a live speed benchmark or proof of semantic OCR accuracy.

## Update

```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File judge/enable-code.ps1
```

After updating, retry preparation if a running job was marked interrupted by the restart. Do not delete volumes or upload many copies of the same file. The existing model cache and source data stay in their volumes.

If a file still takes unusually long, run this on the computer doing the upload while it is slow:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml exec -T app python scripts/check_preparation.py
docker compose --env-file judge/.env.judge -f judge/compose.yaml logs --tail=120 app
```

The diagnostic makes no model calls, prints no credentials or document text, and reports whether time is in the queue, reading, model loading or indexing. Comparing the same file after warm-up is necessary before claiming a regression or a particular speed-up.
