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

$workDirectory = Join-Path $repoRoot "artifacts\maxwell2d\$Release-$Edition"
New-Item -ItemType Directory -Force -Path $workDirectory | Out-Null
# Run beside a copy of -Project, not the original, so runs/ stays out of the
# git-tracked tests/fixtures/ tree for the default fixture.
$projectCopy = Join-Path $workDirectory (Split-Path -Leaf $Project)
Copy-Item -Path $Project -Destination $projectCopy -Force
$evidence = Join-Path $workDirectory 'generation-manifest.json'

$arguments = @(
    '-m', 'tools.generate_maxwell2d',
    '--project', $projectCopy,
    '--work-directory', $workDirectory,
    '--evidence', $evidence
)
if ($Graphical) { $arguments += '--graphical' }

& "$repoRoot\.venv\Scripts\python.exe" @arguments
exit $LASTEXITCODE
