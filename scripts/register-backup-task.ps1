# Legt die geplante Aufgabe an, die täglich die Backups von manucloud holt.
# Einmalig ausführen (normale PowerShell genügt für das eigene Konto):
#   powershell -ExecutionPolicy Bypass -File scripts\register-backup-task.ps1

$ErrorActionPreference = "Stop"

$TaskName = "UltimateTracker Backup-Abholung"
$Script = "D:\Projekte\UltimateTracker\scripts\pull-manucloud-backups.ps1"

if (-not (Test-Path $Script)) { throw "Skript nicht gefunden: $Script" }

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$Script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 04:30
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Force `
    -Description "Holt die Backups der Server-Maschine (manucloud) auf diesen Rechner" | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Output "Aufgabe eingerichtet: $($task.TaskName)"
Write-Output "  Zeitplan:  täglich 04:30"
Write-Output "  Nächster Lauf: $($info.NextRunTime)"
