param(
    [int]$OllamaPid = 0,
    [int]$RecipePid = 0,
    [int]$StreamlitPid = 0,
    [switch]$WithOllama
)

$ErrorActionPreference = "SilentlyContinue"

$pidFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "service.pids"
$streamlitPidFile = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "streamlit.pids"

if (Test-Path $pidFile) {
    Get-Content $pidFile | ForEach-Object {
        if ($_ -match "^OLLAMA_PID=(\d+)") { $OllamaPid = [int]$Matches[1] }
        if ($_ -match "^RECIPE_PID=(\d+)") { $RecipePid = [int]$Matches[1] }
    }
    Remove-Item $pidFile -ErrorAction SilentlyContinue
}

if (Test-Path $streamlitPidFile) {
    Get-Content $streamlitPidFile | ForEach-Object {
        if ($_ -match "^STREAMLIT_PID=(\d+)") { $StreamlitPid = [int]$Matches[1] }
    }
    Remove-Item $streamlitPidFile -ErrorAction SilentlyContinue
}

if ($RecipePid -gt 0) {
    Write-Host "Stopping recipe service: $RecipePid"
    Stop-Process -Id $RecipePid -ErrorAction SilentlyContinue
}

if ($WithOllama -and $OllamaPid -gt 0) {
    Write-Host "Stopping Ollama: $OllamaPid"
    Stop-Process -Id $OllamaPid -ErrorAction SilentlyContinue
}

if ($StreamlitPid -gt 0) {
    Write-Host "Stopping Streamlit: $StreamlitPid"
    Stop-Process -Id $StreamlitPid -ErrorAction SilentlyContinue
}

if ($RecipePid -eq 0 -and $OllamaPid -eq 0 -and $StreamlitPid -eq 0) {
    Write-Host "No process IDs found. Stop services by PID if started manually."
} else {
    Write-Host "Stop command sent."
}
