# Run Aura locally — judge test build

Aura is a personalized AI tutor built with Vite, FastAPI, PostgreSQL/pgvector and NVIDIA Nemotron through Nebius Token Factory. This download runs on the judge's computer; it does not depend on the author's laptop or require a cloud hosting subscription.

## Before you start

- Install and start **Docker Desktop with Linux containers**, or Docker Engine on Linux. Use **Docker Compose 2.24 or newer** (`docker compose version`).
- Recommended: 16 GB RAM, at least 20 GB free disk space, and an internet connection for dependency/model downloads and Token Factory requests. These are recommendations, not benchmarked minimums. CPU inference and the first setup can take several minutes.
- Get the **judge-only Token Factory credential from the private Devpost testing instructions**. Judges should not have to purchase credits. If that credential is missing, contact the entrant; a public download without model access is not a complete judging handoff.
- Download `Aura-Judge-Build.zip` from [GitHub Releases](https://github.com/Bhavishya007-bit/Aura-NVIDIA/releases), extract it, and open a terminal in the extracted `Aura-Judge-Build` folder. Keep the folder; it contains your private local configuration after setup.

## Start on Windows (PowerShell)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\judge\start.ps1
```

This bypass applies to this script process only. Read the scripts before running them. When prompted, paste the private judge Token Factory key. Input is hidden. The browser opens at **http://localhost:8888** after the server is healthy; the terminal prints the local demo email and password.

## Start on macOS or Linux

```bash
bash judge/start.sh
```

Enter the private judge Token Factory key at the hidden prompt, then open **http://localhost:8888**. The terminal prints your local demo login. Docker on Linux must be accessible to your user.

## First two minutes in Aura

1. Log in using the local demo credentials printed by setup.
2. Wait until **Aura Demo Study Notes.pdf** finishes preparing. The first preparation downloads the real Qwen embedding model; do not ask questions until the material is ready.
3. Select that material. In Tutor, ask **“Explain separate chaining and open addressing with a worked example.”** Inspect the page citations.
4. Open Study Plan and ask **“Create a 3-day revision plan, 20 minutes per day, covering these notes.”** Leave the page and return to check that the run persists. Open Today and complete a task.
5. Try flashcards or a short assessment. Try Stop during an active generation, then edit and resend.

`SAMPLE_STUDY_NOTES.md` contains the same original synthetic topics for inspection. No real student documents, personal database or recorded model outputs are shipped. The demo account is synthetic and cannot upload personal files. To test your own material, register a separate local account through the sign-in screen.

## Images and diagrams (optional first-start option)

For screenshots and diagram interpretation, include the local vision model during the **first setup**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\judge\start.ps1 -Vision
```

```bash
bash judge/start.sh --vision
```

This downloads Gemma 3 4B through Ollama and needs additional disk/RAM. Text study does not require it. If you already configured Aura, stop it, change `AURA_JUDGE_VISION_MODEL=''` to `AURA_JUDGE_VISION_MODEL='gemma3:4b'` in your private `judge/.env.judge`, and start again. No image model download is included in the ZIP. Image understanding is unavailable until that model is installed; OCR alone is not equivalent to diagram understanding.

## Available features and optional services

| Feature | Local judge build |
| --- | --- |
| Tutor, source citations, summaries, notes, flashcards, assessments | Included; requires the supplied Token Factory credential and prepared material |
| Study plans, tasks, memory, cancellation, saved runs | Included; uses this installation's own database |
| Screenshots/diagrams | Enable the vision option above |
| Web research | Optional Tavily key in local `judge/.env.judge`; without it, external web search is unavailable |
| Code & Data execution | **Disabled in this one-command container profile.** The source includes the tested local Docker sandbox setup in [docs/CODE_ANALYSIS.md](docs/CODE_ANALYSIS.md). Use the native developer setup for that feature; do not mount your host Docker socket into the web container. Execution is shown separately in the demo video. |

The tested Nemotron Ultra model identifier is written to the private local config. There is no automatic model downgrade. If the provided key cannot access it, the entrant must correct the credential/model access before judging. Generation limits are explicit local safety budgets, not a guarantee that a 2,000-word request always succeeds; long-answer quality and human judge calibration remain under evaluation.

## Stop and return later

Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File .\judge\stop.ps1`

macOS/Linux: `bash judge/stop.sh`

Run the same start command next time. Existing credentials and the separate `aura-judge` Docker volumes are preserved. Stopping the containers does not delete your data. Your existing Aura development database and `backend/.env` are not used or changed. Only port 8888 is exposed, on localhost; the database and vision service have no published ports.

## Troubleshooting

- **Docker not available:** start Docker Desktop, select Linux containers, and run `docker info`. On Linux, check your Docker user permissions.
- **Port 8888 occupied:** stop the other service using it before retrying. Do not publish Aura on all network interfaces.
- **First startup takes time:** dependency downloads and real embedding/vision models are large. Wait for preparation to finish. No model has been replaced with a fake or smaller encoder for the download.
- **Model request fails:** check internet connectivity and ask the entrant to verify the privately supplied Token Factory key has model access and remaining credits. Do not post the key or `.env.judge` in an issue.
- **Server diagnostics:** from the `judge` directory run `docker compose --env-file .env.judge -f compose.yaml logs --tail 60 app`. Review logs before sharing; do not send environment dumps or `docker compose config` output containing credentials.
- **Read the local login again:** rerun the start script. It preserves your settings and prints only the local demo login.
- **Tutor gives only outside knowledge or an excerpt fallback:** see [the source-retention update](docs/TUTOR_SECTIONS.md). After pulling source changes, rebuild the Docker app; an already-running image does not update from Git pull alone. Test a new question and inspect its citations.

See [docs/JUDGE_SUBMISSION.md](docs/JUDGE_SUBMISSION.md) for the entrant's release and private testing-access checklist. The public package never contains a provider key.
