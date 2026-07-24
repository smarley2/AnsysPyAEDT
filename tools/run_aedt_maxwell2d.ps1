[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('2025.2')]
    [string]$Release,

    [Parameter(Mandatory = $true)]
    [ValidateSet('commercial')]
    [string]$Edition,

    [string]$Project = "tests\fixtures\sample_geometry_project.inductor.json",

    [switch]$Graphical
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$outputDirectory = Join-Path $repoRoot "artifacts\maxwell2d\$Release-$Edition"
$evidence = Join-Path $outputDirectory 'generation-manifest.json'

$arguments = @(
    '-m', 'tools.generate_maxwell2d',
    '--project', $Project,
    '--output-directory', $outputDirectory,
    '--evidence', $evidence,
    '--force-2d'
)
if ($Graphical) { $arguments += '--graphical' }

& "$repoRoot\.venv\Scripts\python.exe" @arguments
exit $LASTEXITCODE
