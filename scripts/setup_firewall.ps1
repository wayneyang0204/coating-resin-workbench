param(
    [int]$ApiPort = 8088,
    [int]$OllamaPort = 11434
)

$ErrorActionPreference = "Stop"

try {
    if (-not (Get-NetFirewallRule -DisplayName "Allow_Ollama_$OllamaPort" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "Allow_Ollama_$OllamaPort" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $OllamaPort -Enabled True | Out-Null
        Write-Host "Created firewall rule for Ollama: port $OllamaPort"
    } else {
        Write-Host "Ollama rule already exists."
    }

    if (-not (Get-NetFirewallRule -DisplayName "Allow_RecipeAPI_$ApiPort" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "Allow_RecipeAPI_$ApiPort" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ApiPort -Enabled True | Out-Null
        Write-Host "Created firewall rule for Recipe API: port $ApiPort"
    } else {
        Write-Host "Recipe API rule already exists."
    }
} catch {
    Write-Warning "Firewall change needs admin permission. Run this script as administrator."
    Write-Host $_.Exception.Message
}
