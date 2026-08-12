param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [Parameter(Mandatory=$true)][string]$LogDirectory
)
$ErrorActionPreference = 'Stop'
foreach ($path in @($ProjectRoot, $PythonExe, $ConfigPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path does not exist: $path" }
}
$resolvedRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonExe).Path
$resolvedConfig = (Resolve-Path -LiteralPath $ConfigPath).Path
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$env:PYTHONPATH = Join-Path $resolvedRoot 'src'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdout = Join-Path $LogDirectory "collection_$stamp.out.log"
$stderr = Join-Path $LogDirectory "collection_$stamp.err.log"
& $resolvedPython -m hmr_order_collection.orchestrator --config $resolvedConfig 1> $stdout 2> $stderr
$exitCode = $LASTEXITCODE
exit $exitCode
