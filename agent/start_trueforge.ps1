$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:HOST = '127.0.0.1'
$env:STANDALONE = 'true'
$env:OUTBOUND_URL_ALLOWED_HOSTS = '["127.0.0.1"]'
$env:SQLITE_PATH = Join-Path $projectRoot '.runtime\trueforge.sqlite'
$cliPath = Join-Path $projectRoot '.runtime\trueforge\node_modules\@truefoundry\trueforge\dist\cli.js'
if (-not (Test-Path -LiteralPath $cliPath)) {
    throw 'Install TrueForge first: npm install --prefix .runtime/trueforge --save-exact @truefoundry/trueforge@0.182.0'
}
& node $cliPath --port 8790
