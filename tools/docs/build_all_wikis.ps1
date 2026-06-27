param(
    [switch]$Check,
    [switch]$BrowserSmoke
)

$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$CardCheck = Join-Path $PSScriptRoot 'check_okf_route_cards.py'
$Script = Join-Path $PSScriptRoot 'build_okf_wikis.py'
& python $CardCheck --repo $RepoRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$Args = @($Script, '--repo', $RepoRoot)
if ($Check) { $Args += '--check' }
if ($BrowserSmoke) { $Args += '--browser-smoke' }
& python @Args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
