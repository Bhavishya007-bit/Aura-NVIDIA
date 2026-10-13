param([string]$Model = 'gemma3:4b')
$ErrorActionPreference = 'Stop'
if ($Model -notmatch '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,120}$') { throw 'Invalid Ollama model name.' }
$root = Split-Path -Parent $PSScriptRoot
$config = Join-Path $root 'backend\.env'
if (!(Test-Path -LiteralPath $config)) { throw 'Keep your existing backend/.env; create the normal local configuration first.' }
$content = [System.IO.File]::ReadAllText($config)
$backup = Join-Path $root ('aura-update-backups\vision-config-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Copy-Item -LiteralPath $config -Destination (Join-Path $backup 'backend.env')
$line = 'OLLAMA_VISION_MODEL=' + $Model
if ($content -match '(?m)^\s*OLLAMA_VISION_MODEL\s*=') {
    $content = [regex]::Replace($content, '(?m)^\s*OLLAMA_VISION_MODEL\s*=.*$', $line)
} else { $content = $content.TrimEnd() + "`r`n" + $line + "`r`n" }
[System.IO.File]::WriteAllText($config, $content, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "Configured $Model for figure interpretation. Install the model with 'ollama pull $Model' if needed and restart the backend."
