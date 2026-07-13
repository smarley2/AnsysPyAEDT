[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:2024\.2|20(?:2[5-9]|[3-9][0-9])\.[12])$')]
    [string]$Release,

    [Parameter(Mandatory = $true)]
    [ValidateSet('commercial', 'student')]
    [string]$Edition,

    [switch]$Graphical
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$runDirectory = Join-Path $root "artifacts/compatibility/$Release-$Edition"
$projectDirectory = Join-Path $runDirectory 'projects'
$evidencePath = Join-Path $runDirectory 'evidence.json'

$arguments = @(
    '-m', 'tools.aedt_spike',
    '--release', $Release,
    '--edition', $Edition,
    '--output-directory', $projectDirectory,
    '--evidence', $evidencePath
)
if ($Graphical) {
    $arguments += '--graphical'
}

Push-Location $root
try {
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AEDT compatibility spike failed with exit code $LASTEXITCODE"
    }
    Write-Host "Evidence written to $evidencePath"
}
finally {
    Pop-Location
}
