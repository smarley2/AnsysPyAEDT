[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{12}$')]
    [string]$Revision
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$release = '2025.2'
$edition = 'commercial'
$manufacturer = 'Magnetics'
$materialName = 'High Flux'
$grade = '60'
$corePartNumber = 'C058071A2'
$bhSeriesId = 'bh-25c'
$overlayRoot = Join-Path $repoRoot 'materials-overlay'
$schemasRoot = Join-Path $repoRoot 'schemas'
$validationRoot = Join-Path $repoRoot 'artifacts\material-validation'
$projectPath = Join-Path $validationRoot 'm5a-high-flux-60.inductor.json'
$evidencePath = Join-Path $validationRoot 'preflight.json'
$liveRoot = Join-Path $validationRoot 'live'
$catalogPath = Join-Path $repoRoot 'artifacts\catalog\catalog.sqlite'
$baseProject = Join-Path $repoRoot 'tests\fixtures\sample_geometry_project.inductor.json'
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Python environment not found: $python"
}

& $python -m tools.build_catalog --out $catalogPath
if ($LASTEXITCODE -ne 0) {
    throw "Catalog build failed with exit code $LASTEXITCODE."
}

& $python -m tools.reproduce_material `
    --overlay-root $overlayRoot `
    --manufacturer $manufacturer `
    --name $materialName `
    --grade $grade `
    --revision $Revision
if ($LASTEXITCODE -ne 0) {
    throw "Material reproduction failed with exit code $LASTEXITCODE."
}

& $python -m tools.prepare_material_handoff `
    --base-project $baseProject `
    --catalog $catalogPath `
    --schemas $schemasRoot `
    --overlay-root $overlayRoot `
    --manufacturer $manufacturer `
    --name $materialName `
    --grade $grade `
    --revision $Revision `
    --core-part-number $corePartNumber `
    --bh-series-id $bhSeriesId `
    --output-project $projectPath `
    --evidence $evidencePath
if ($LASTEXITCODE -ne 0) {
    throw "Material handoff preparation failed with exit code $LASTEXITCODE."
}

if (Test-Path -LiteralPath $liveRoot) {
    Remove-Item -LiteralPath $liveRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $liveRoot -Force | Out-Null

$env:INDUCTOR_M5A_PROJECT = $projectPath
$env:INDUCTOR_M5A_ARTIFACT_ROOT = $liveRoot
$env:INDUCTOR_AEDT_RELEASE = $release
$env:INDUCTOR_AEDT_EDITION = $edition
$env:INDUCTOR_FEMM_LIVE = '1'

& $python -m pytest `
    tests\integration\aedt\test_material_handoff.py `
    tests\integration\femm\test_material_handoff.py `
    -vv
if ($LASTEXITCODE -ne 0) {
    throw "M5a live solver validation failed with exit code $LASTEXITCODE."
}

Write-Host "M5a live validation completed."
Write-Host "Evidence: $evidencePath"
Write-Host "Live artifacts: $liveRoot"
