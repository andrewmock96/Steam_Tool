# Registers (or re-registers) the daily Windows Task Scheduler job that keeps
# the "coming soon" data fresh: adds newly-flagged coming_soon games, marks
# games as launched once they ship, and backfills Steam store tags for
# anything still missing them.
#
# Run once to install:
#   powershell -ExecutionPolicy Bypass -File setup_daily_task.ps1
#
# Runs only while this machine is logged in as the current user (no admin
# rights or "run whether logged on or not" needed, which keeps python.exe's
# Windows Store app-execution-alias working normally).

$TaskName = "GoingIndie-DailyUpcomingSync"
$ScriptDir = $PSScriptRoot
$BatPath = Join-Path $ScriptDir "run_daily_upcoming_sync.bat"

$Action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $ScriptDir
$Trigger = New-ScheduledTaskTrigger -Daily -At 6:00AM
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal `
    -Description "Daily sync of Steam coming-soon games: add new, mark launched, backfill tags."

Write-Host "Registered scheduled task '$TaskName' to run daily at 6:00 AM."
Write-Host "Logs will accumulate in logs\upcoming_sync.log"
