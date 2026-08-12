param(
    [Parameter(Mandatory=$true)][string]$ProjectRoot,
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$ConfigPath,
    [string]$LogDirectory = 'C:\ProgramData\HMR_Order_Collection\logs',
    [string]$TaskName = 'HMR Daily Order Collection',
    [switch]$ValidateOnly
)
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $ProjectRoot 'scripts\windows\run_daily_order_collection.ps1'
foreach ($path in @($ProjectRoot, $PythonExe, $ConfigPath, $launcher)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path does not exist: $path" }
}
$arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$launcher`" -ProjectRoot `"$ProjectRoot`" -PythonExe `"$PythonExe`" -ConfigPath `"$ConfigPath`" -LogDirectory `"$LogDirectory`""
if ($ValidateOnly) {
    [pscustomobject]@{ TaskName=$TaskName; Schedule='Daily 14:00'; Principal='SYSTEM'; Launcher=$launcher; PythonExe=$PythonExe; ConfigPath=$ConfigPath }
    exit 0
}
$action = New-ScheduledTaskAction -Execute 'PowerShell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -Daily -At '14:00'
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Daily HMR channel order collection with DB audit history' -Force | Out-Null
