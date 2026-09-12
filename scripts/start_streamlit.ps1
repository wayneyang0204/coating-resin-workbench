param(
    [int]$StreamlitPort = 8501,
    [string]$BindHost = "0.0.0.0"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$appScript = Join-Path $repoRoot "app.py"
$pidFile = Join-Path $PSScriptRoot "streamlit.pids"
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }

if (-not (Test-Path $appScript)) {
    throw "找不到 app.py：$appScript"
}

$env:TECH_DB_API_BASE = "http://127.0.0.1:8765"
$proc = Start-Process -FilePath $pythonExe -ArgumentList @("-m", "streamlit", "run", $appScript, "--server.port", "$StreamlitPort", "--server.address", $BindHost) -WorkingDirectory $repoRoot -PassThru

Set-Content -Path $pidFile -Value @"
STREAMLIT_PID=$($proc.Id)
"@

Write-Host "Streamlit started: http://$BindHost`:$StreamlitPort"
Write-Host "Stop with: .\scripts\stop_all.ps1"
