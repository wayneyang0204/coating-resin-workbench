param(
    [string]$CsvPath = ".\\data\\sample_recipes.csv"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $CsvPath)) {
    throw "CSV file not found: $CsvPath"
}

$rows = Import-Csv -Path $CsvPath
foreach ($r in $rows) {
    $body = @{
        name = $r.name
        ingredients = $r.ingredients
        steps = $r.steps
        tags = $r.tags
        serving = [int]$r.serving
    } | ConvertTo-Json -Depth 3

    try {
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8088/api/recipes" -Body $body -ContentType "application/json" | Out-Null
        Write-Host "Imported: $($r.name)"
    } catch {
        Write-Warning "Import failed: $($r.name), $($_.Exception.Message)"
    }
}

Write-Host "Import finished."
