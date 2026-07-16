[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(?:2024\.2|20(?:2[5-9]|[3-9][0-9])\.[12])$')]
    [string]$Release,

    [Parameter(Mandatory = $true)]
    [ValidateSet('commercial', 'student')]
    [string]$Edition,

    [string]$Project = "tests\fixtures\sample_geometry_project.inductor.json",

    [switch]$Graphical
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$outputDirectory = Join-Path $repoRoot "artifacts\maxwell3d\$Release-$Edition"
$evidence = Join-Path $outputDirectory 'generation-manifest.json'

$arguments = @(
    '-m', 'tools.generate_maxwell3d',
    '--project', $Project,
    '--output-directory', $outputDirectory,
    '--evidence', $evidence
)
if ($Graphical) { $arguments += '--graphical' }

& "$repoRoot\.venv\Scripts\python.exe" @arguments
exit $LASTEXITCODE
