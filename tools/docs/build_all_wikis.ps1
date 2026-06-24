param(
    [switch]$Check,
    [switch]$BrowserSmoke
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$Script = Join-Path $PSScriptRoot 'build_okf_wikis.py'
$Args = @($Script, '--repo', $RepoRoot)
if ($Check) { $Args += '--check' }
if ($BrowserSmoke) { $Args += '--browser-smoke' }
& python @Args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
