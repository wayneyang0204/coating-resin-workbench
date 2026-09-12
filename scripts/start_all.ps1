param(
    [string]$BindHost = "0.0.0.0",
    [int]$OllamaPort = 11434,
    [int]$ApiPort = 8088,
    [switch]$WithStreamlit = $false
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\\Ollama\\ollama.exe"
$pidFile = Join-Path $PSScriptRoot "service.pids"
$webFolder = Join-Path $repoRoot "web"
$recipeScript = Join-Path $repoRoot "recipe_server.py"

if (-not (Test-Path $ollamaExe)) {
    throw "Cannot find Ollama executable: $ollamaExe"
}

if (-not (Test-Path $webFolder)) {
    throw "Cannot find web folder: $webFolder"
}

if (-not (Test-Path $recipeScript)) {
    throw "Cannot find recipe_server.py: $recipeScript"
}

$existingOllama = Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $ollamaExe }
if (-not $existingOllama) {
    Write-Host "Starting Ollama..."
    $ollamaProc = Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden -PassThru
    $ollamaPid = $ollamaProc.Id
} else {
    $ollamaPid = $existingOllama[0].Id
}

Set-Item -Path Env:OLLAMA_HOST -Value "$BindHost`:$OllamaPort"
Set-Item -Path Env:OLLAMA_ORIGINS -Value "*"
Set-Item -Path Env:OLLAMA_NUM_PARALLEL -Value "4"
Set-Item -Path Env:OLLAMA_KEEP_ALIVE -Value "30m"
Set-Item -Path Env:OLLAMA_MAX_LOADED_MODELS -Value "2"

Set-Item -Path Env:OLLAMA_URL -Value "http://127.0.0.1:$OllamaPort"
Set-Item -Path Env:OLLAMA_MODEL -Value "qwen2.5:7b-tw"
Set-Item -Path Env:RECIPE_HOST -Value "0.0.0.0"
Set-Item -Path Env:RECIPE_PORT -Value "$ApiPort"
Set-Item -Path Env:RECIPE_DB_PATH -Value (Join-Path $repoRoot "recipes.db")
Set-Item -Path Env:TECH_DB_API_BASE -Value "http://127.0.0.1:8765"

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) { $pythonExe = "python" }
$apiProc = Start-Process -FilePath $pythonExe -ArgumentList $recipeScript -PassThru
$streamlitProc = $null

if ($WithStreamlit) {
    $appScript = Join-Path $repoRoot "app.py"
    if (-not (Test-Path $appScript)) {
        Write-Host "找不到 Streamlit 前端：$appScript"
    } else {
        $streamlitExe = Get-Command streamlit -ErrorAction SilentlyContinue
        if (-not $streamlitExe) {
            throw "找不到 streamlit 指令，請先安裝：python -m pip install -r requirements.txt"
        }
        Write-Host "Starting Streamlit..."
        $streamlitProc = Start-Process -FilePath $streamlitExe.Source -ArgumentList @("run", $appScript, "--server.port", "8501", "--server.address", "0.0.0.0") -WindowStyle Hidden -PassThru
    }
}

Set-Content -Path $pidFile -Value @"
OLLAMA_PID=$ollamaPid
RECIPE_PID=$($apiProc.Id)
"@

if ($streamlitProc) {
    Add-Content -Path $pidFile -Value "STREAMLIT_PID=$($streamlitProc.Id)"
    Write-Host "Streamlit UI started: http://localhost:8501"
}

Write-Host "Recipe API started: http://$BindHost`:${ApiPort}"
Write-Host "Stop with: .\\scripts\\stop_all.ps1"
if ($streamlitProc) {
    Write-Host "Stop with: .\\scripts\\stop_all.ps1 -RecipePid 0 -OllamaPid $ollamaPid"
}
Wait-Process -Id $apiProc.Id
