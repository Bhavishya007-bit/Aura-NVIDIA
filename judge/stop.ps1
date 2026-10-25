$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& docker compose --env-file .env.judge -f compose.yaml --profile vision down
if ($LASTEXITCODE -ne 0) { throw 'Could not stop Aura. Check Docker Desktop.' }
Write-Host 'Aura stopped. Your local plans, study materials and account are preserved.'
