param([string]$Model = 'gemma3:4b')
$ErrorActionPreference = 'Stop'
if ($Model -notmatch '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,120}$') { throw 'Invalid Ollama model name.' }
$root = Split-Path -Parent $PSScriptRoot
$config = Join-Path $root 'backend\.env'
if (!(Test-Path -LiteralPath $config)) { throw 'Create your normal backend/.env first. This setup preserves existing database credentials.' }
Get-Command ollama -ErrorAction Stop | Out-Null
& ollama pull $Model
if ($LASTEXITCODE -ne 0) { throw 'Vision model download failed. Check Ollama and your connection before continuing.' }
# This existing script backs up the complete previous .env before changing it.
& (Join-Path $PSScriptRoot 'configure_vision.ps1') -Model $Model
$content = [System.IO.File]::ReadAllText($config)
foreach ($setting in @(@('WHISPER_MODEL_SIZE', 'small.en'), @('WHISPER_LANGUAGE', 'en'))) {
    $key = $setting[0]
    $line = $key + '=' + $setting[1]
    if ($content -match ('(?m)^\s*' + $key + '\s*=')) {
        $content = [regex]::Replace($content, ('(?m)^\s*' + $key + '\s*=.*$'), $line)
    } else {
        $content = $content.TrimEnd() + "`r`n" + $line + "`r`n"
    }
}
[System.IO.File]::WriteAllText($config, $content, (New-Object System.Text.UTF8Encoding($false)))
Write-Host 'Gemma vision and small.en English transcription are configured on THIS laptop.'
Write-Host 'Database, text model and CPU/GPU device settings were preserved. The previous .env is backed up.'
Write-Host 'Stop the old backend and restart from the Aura root. Run scripts/check_multimodal.py afterward.'
Write-Host 'Whisper downloads its weights on first use. Prepare fresh copies of videos with poor old transcripts.'
