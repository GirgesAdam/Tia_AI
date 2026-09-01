$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
$patterns = @("APPLY_v*.md","PATCH_MANIFEST*.txt","DELETIONS*.txt","CLEANUP_v*.ps1","MANIFEST.txt","AGENT_SETUP.md")
foreach ($pattern in $patterns) {
  Get-ChildItem -Path $root -File -Filter $pattern -ErrorAction SilentlyContinue | Remove-Item -Force
}
if (Test-Path (Join-Path $root ".idea")) { Remove-Item -Recurse -Force (Join-Path $root ".idea") }
Write-Host "GitHub repository workspace cleaned. Local env files remain gitignored."
