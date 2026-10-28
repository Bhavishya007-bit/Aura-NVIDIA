# Personal accounts by default

Normal Aura sign-up is now the default for the local Docker package. There is no required shared judge login and no automatic sample-document seed. The existing optional synthetic demo is still available only when an operator explicitly sets `AURA_JUDGE_DEMO_ENABLED=true`. Old demo accounts, personal accounts and uploaded files are not deleted or merged. Existing personal users should keep using their accounts; someone using the old restricted demo should sign out and create a personal Aura account to upload their own material.

The email is an Aura sign-in identifier. Aura does not sign in to Gmail, and the user should choose a new Aura password rather than provide an email-account password. PostgreSQL workspace/account isolation and the existing sign-in APIs are preserved.

## Updates

```powershell
git pull origin main
powershell -ExecutionPolicy Bypass -File judge/enable-code.ps1
```

This keeps Code & Data enabled with the existing isolated local execution service. Without that optional service, use the standard Compose rebuild documented in `JUDGE_QUICKSTART.md`. After startup, open `/signup` for a new account or sign in with an existing personal account. No material is required just to sign in or open memory settings. Study generation requires a selected ready material.

## Check a teammate's installation

Run on the computer where the failure happens:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml exec -T app python scripts/check_features.py --live
```

The check reads schema presence and the running API's route list, then sends one small JSON request to each configured model role. It prints no credentials or document contents and does not modify accounts or documents. The live requests consume a small amount of provider credit. Without `--live`, the check makes no model requests. It is not a guarantee of model accuracy or a replacement for a live document-generation test.

A shared-account setting does not by itself explain a memory GET failure or a generation failure for a PDF. The screenshots do not reveal HTTP status/provider warnings. The new check distinguishes installation/schema/route failures from provider configuration failures so the cause can be fixed rather than hidden.

## Error recovery changes

- Successful memory reload now clears an earlier error; switching/retrying resets the loading state, and controls remain disabled until records really load.
- Memory failures give actionable categories without exposing raw exceptions or pretending the memory list is empty.
- Capability errors only fall back to older single-material tools on a genuine missing endpoint (404). Network, permissions, invalid responses and server errors are surfaced as an availability notice instead of silently downgrading.
- Existing DOCX excerpt-citation and upload/video progress fixes remain included.
- The production CI smoke runs the non-live feature schema/route check. Personal-account flows, generation, source support and account-specific memory still require real-user verification.
