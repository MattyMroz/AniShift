# Manual end-to-end smoke for the composition stage.
# Set the output variant in /settings first, then run this script and press Enter
# (full pipeline) or type /compose (assembly only) in the shell it starts.
# Usage: .\scripts\smoke\run_e2e.ps1
$ErrorActionPreference = "Stop"

$workspace = Join-Path $PSScriptRoot "..\..\workspace"
$sources = @(Get-ChildItem -Path $workspace -Filter *.mkv -File | Where-Object { $_.Name -notlike "*.pl.mkv" })
if ($sources.Count -eq 0) { throw "No MKV in workspace/." }

Write-Host ("Sources: {0}" -f $sources.Count)
foreach ($source in $sources) {
    Write-Host ("  {0} ({1} MB)" -f $source.Name, [math]::Round($source.Length / 1MB, 1))
}

uv run anishift

$output = Join-Path $workspace "output"
Write-Host "`nResults in output/:"
if (Test-Path $output) {
    Get-ChildItem -Path $output -File | ForEach-Object {
        Write-Host ("  {0} ({1} MB)" -f $_.Name, [math]::Round($_.Length / 1MB, 1))
    }
}

Write-Host "`nProducts next to the sources:"
Get-ChildItem -Path $workspace -File -Include *.pl.ass, *.pl.srt, *.eac3 -Recurse -Depth 0 | ForEach-Object {
    Write-Host ("  {0}" -f $_.Name)
}
