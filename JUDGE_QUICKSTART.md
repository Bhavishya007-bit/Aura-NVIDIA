# Run Aura locally

Aura uses normal personal accounts. No shared judge email, Gmail password, or preloaded document is required.

## Start

1. Install and open Docker Desktop with Linux containers. Allow roughly 20 GB disk space and use an internet connection for dependencies and models.
2. On Windows, run `powershell -ExecutionPolicy Bypass -File judge/start.ps1` from the repository folder. On Linux/macOS use `bash judge/start.sh`.
3. Setup asks privately for the Token Factory API key. For judging, the organizer/project owner supplies a dedicated key through private testing instructions; judges should not need to buy credits. This is an API credential, not an email password.
4. Open `http://localhost:8888/signup`, create your own Aura account and choose a new password. Upload a PDF, DOCX or another supported material and wait until it is ready.
5. Use Tutor, Notes, Summary, Flashcards, Assessment, Progress or Study Plan. Each account has its own material and memory.

Existing users can keep using their personal accounts. Existing settings and saved data are not deleted. The optional synthetic demo is disabled by default. Advanced operators can explicitly set `AURA_JUDGE_DEMO_ENABLED=true` if they want the separate restricted demo account; no demo password belongs in the repository or video.

## Update and check

```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File judge/enable-code.ps1
```

The optional Code & Data setup starts a privileged local Docker execution service without a host socket mount; see `docs/WORKSPACE_MOTION.md`. For the standard build without code execution, use `docker compose --env-file judge/.env.judge -f judge/compose.yaml up -d --build app` instead.

After Aura has started, run a read-only backend/schema check and small real requests to each configured model:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml exec -T app python scripts/check_features.py --live
```

This checks configuration, not universal answer accuracy. Test with your actual material afterward. If a feature fails, share the check output and relevant backend warning lines, never the `.env.judge` file. No failed generation is replaced with an invented answer or empty memory result.

Files are limited to 100 MiB each. Compress/split larger videos or upload their transcript. Initial downloads and CPU preparation can take several minutes. The app and database use persistent Docker volumes; do not delete them to troubleshoot.

## Optional vision

Start with `judge/start.ps1 -Vision` (or `judge/start.sh --vision`) to prepare the local vision model. Web research also needs the optional Tavily configuration. Python execution is enabled separately as above. These options do not require a shared Aura account.
