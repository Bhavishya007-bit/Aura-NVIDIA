# Signed-in workspace and local Code & Data

Progress now uses actual API quiz scores in an SVG trend chart (with an exact-value table), lower-mastery topic bars, a visual next-step card and the existing mastery, streak, time, cards, topic map and history. Empty states show no invented data. Existing practice callbacks and API routes are unchanged.

Files: `src/components/ProgressVisuals.tsx`, `src/components/ProgressV2.tsx`, `src/components/WorkspaceMotion.css`, `src/components/StudyWorkspace.tsx`.

Workspace navigation, tool cards, primary actions and sections have hover/press/entrance motion. Progress has subtle orbit/glow motion, paused offscreen or in hidden tabs. Reduced-motion disables animations. Charts preserve accessible exact-value tables and don't imply a causal improvement from a small sample.

## Enable Python in the local Docker build

From the Aura-NVIDIA folder in PowerShell, with Docker Desktop running:

```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File judge/enable-code.ps1
```

The script starts the app with `judge/compose.code.yaml`, waits for a prepared Python sandbox image, then runs an actual isolated CSV/Python smoke check. It makes no model calls for that check. Refresh the browser only after the check succeeds. Future updates with code enabled should use the same script, or include both Compose files.

This optional setup uses a **privileged Docker-in-Docker service**, intended for a trusted local laptop, not public hosting. It does not mount the host Docker socket, any host directories, account secrets, or the app's material volume into the execution service. Its unencrypted daemon API is on an internal Docker network and has no published host port. The service needs internet to download the initial Python image; generated Python guests run with no network, read-only filesystems, no added capabilities and existing CPU/memory/time limits. A separate daemon reduces exposure but is not a VM security boundary. The standard judge package remains disabled until this setup is explicitly run.

Files: `Dockerfile` (Docker CLI only), `judge/code/Dockerfile`, `judge/code/start.sh`, `judge/compose.code.yaml`, `judge/enable-code.ps1`. Existing sandbox contracts, cancellation and artifact validation are reused. The setup needs a real local Docker run; frontend capability visibility alone is not an execution test.

Manual checks: dark/light Progress on mobile and 2K, keyboard table disclosure/practice actions, reduced motion, a populated quiz history and empty history, then run “Compare linear and binary search, print comparison counts and save results.json” under Code & data. Verify captured output, download, Stop and cancellation. Do not deploy the local execution overlay to a public host.
