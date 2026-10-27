$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host 'Starting the local isolated Python service. Initial setup downloads a Python image.'
& docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml up -d --build --wait --wait-timeout 600 app
if ($LASTEXITCODE -ne 0) {
    & docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml logs --tail=60 code
    throw 'Code service setup failed. Share the service logs printed above.'
}
& docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml exec -T app python scripts/check_code_runtime.py --smoke
if ($LASTEXITCODE -ne 0) { throw 'Python execution check failed. Code setup is not verified.' }
Write-Host 'Python execution verified. Refresh Aura at http://localhost:8888 and select Code & data.'
