param([switch]$Vision)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
function Invoke-Docker { & docker @args; if ($LASTEXITCODE -ne 0) { throw 'Docker command failed. See the message above.' } }
Invoke-Docker info --format '{{.OSType}}'
Invoke-Docker compose version
$compose = @('compose', '--env-file', '.env.judge', '-f', 'compose.yaml')
if (!(Test-Path '.env.judge')) { New-Item '.env.judge' -ItemType File | Out-Null; $fresh = $true } else { $fresh = $false }
try {
    Write-Host 'Building Aura. The first build downloads dependencies and may take several minutes.'
    Invoke-Docker @compose build app
    if ($fresh) {
        Remove-Item '.env.judge'
        # Bootstrap without --env-file while the helper creates that file.
        $setup = @('compose', '-f', 'compose.yaml', 'run', '--rm', '--no-deps', '--user', '0', '-v', "${PSScriptRoot}:/config", 'app', 'python', 'scripts/configure_judge.py')
        if ($Vision) { $setup += '--vision' }
        Invoke-Docker @setup
    }
    $settings = Get-Content '.env.judge' -Raw
    if ($settings.Contains("AURA_JUDGE_VISION_MODEL='gemma3:4b'")) {
        Invoke-Docker @compose --profile vision up -d vision
        Invoke-Docker @compose exec -T vision ollama pull gemma3:4b
    }
    Invoke-Docker @compose up -d --wait --wait-timeout 240 db app
    Invoke-Docker @compose run --rm --no-deps --user 0 -v "${PSScriptRoot}:/config" app python scripts/configure_judge.py --show-login
    Start-Process 'http://localhost:8888'
} catch {
    if ($fresh -and (Test-Path '.env.judge') -and (Get-Item '.env.judge').Length -eq 0) { Remove-Item '.env.judge' }
    Write-Host 'Setup did not finish. Check Docker Desktop is running (Linux containers), then run this script again.'
    throw
}
