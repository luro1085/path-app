# Registers a Windows Scheduled Task to auto-launch the PATH kiosk app at user logon.
param(
    [Parameter(Mandatory = $true)]
    [string] $AppPath,
    [string] $TaskName = "PATHKiosk",
    [string] $User = "$env:USERNAME"
)

if (-not (Test-Path $AppPath)) {
    Write-Error "AppPath '$AppPath' does not exist. Build the EXE or point to start.bat."
    exit 1
}

$action = New-ScheduledTaskAction -Execute $AppPath -WorkingDirectory (Split-Path $AppPath)
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest

try {
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
    Write-Host "Task '$TaskName' registered to launch at logon for user '$User'."
} catch {
    Write-Error "Failed to register task: $_"
    exit 1
}

