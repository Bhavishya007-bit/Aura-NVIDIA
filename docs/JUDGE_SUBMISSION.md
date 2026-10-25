# Downloadable submission handoff

The official [hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules) allow a working demo, hosted application **or test build**. The test build must install and run consistently on its intended platform, and judging access must remain free through the end of judging. A public repository and public demo video under three minutes are also required. A cloud-hosted copy is not required by that wording.

## What the repository automates

- The judge release workflow tests the local Compose profile, packages an explicit committed tree, and publishes a GitHub **prerelease** with a ZIP and SHA-256 checksum.
- The ZIP includes source, setup/stop scripts, synthetic notes and the MIT license. It excludes local environments, credentials, personal uploads and evaluation reports.
- The launcher builds the frontend/backend, creates isolated local PostgreSQL storage, generates fresh local passwords, and queues original synthetic notes for normal preparation.
- A prerelease is a downloadable test build, **not a declaration that human calibration, live model access or every feature has passed**.

## Entrant actions before submitting

1. Create a **dedicated judging credential** in the Token Factory project you intend to fund. Verify NVIDIA Nemotron Ultra access with the existing model-quality smoke check. Do not distribute a personal account password or put a provider key in the release, README, video, GitHub issue or frontend variables.
2. Put the dedicated credential **only in the private Devpost testing instructions**. It is entered into the judge's local backend config; it is never bundled with the download. Treat this as privileged access: anyone holding an API key can use it directly, bypassing Aura's local token caps. Use provider-enforced restrictions/budgets if your account supports them; do not claim Aura's local limits cap the provider account. If the provider does not permit this credential-sharing method, arrange a compliant protected relay before submission instead.
3. Keep that credential valid and funded for the entire judging period. Recheck the official dates/rules at submission; the rules inspected on October 25 list judging through December 15, 2026 at noon Pacific. Do not rely on promotional credit expiry without checking your actual account.
4. Download the published ZIP on a clean Windows machine. Run `judge/start.ps1`, log in, wait for real preparation, and test one cited answer, a plan, cancellation and a persisted task. Also test macOS/Linux if claiming those platforms. Linux container/browser CI does not verify Windows PowerShell or CPU model throughput.
5. Record and publish the demo video under three minutes. Show real working results. Explicitly distinguish the optional native Code & Data setup from the one-command container profile.
6. Complete the Devpost fields, test-build URL, public source link, video link, private instructions and required feedback/track fields. Submit before the hard deadline. Human coverage calibration is still pending; do not report it as passed.

## Private testing instructions template

Copy this into the **private** testing field, filling in the credential there only:

> Test build: [paste the exact GitHub release URL]. Download Aura-Judge-Build.zip and extract it. Follow JUDGE_QUICKSTART.md. Requires Docker Desktop with Linux containers and Compose 2.24+, internet, recommended 16 GB RAM and 20 GB disk. First setup downloads dependencies and embeddings. Run the Windows PowerShell or macOS/Linux launcher. At its hidden prompt use the judging Token Factory key: [ENTER IN THIS PRIVATE FIELD ONLY]. The launcher prints a fresh local demo login. Open http://localhost:8888 and wait for Aura Demo Study Notes.pdf to become ready. Ask “Explain separate chaining and open addressing with a worked example,” then create a 3-day plan. Optional vision setup is documented; the Code & Data sandbox uses the separate native setup. No purchase is required from judges. Contact: [entrant contact].

Never add a filled-in copy of this template to GitHub. Model access is not configured merely by publishing the ZIP.
