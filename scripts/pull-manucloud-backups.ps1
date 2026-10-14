# Holt die Backups der Server-Maschine (manucloud) auf diesen Rechner.
#
# Warum: Die Sicherungen liegen auf der Maschine auf **derselben SSD**. Ein
# Plattenausfall nimmt damit Daten UND Backups. Dieses Skript zieht eine zweite
# Kopie auf den Windows-Host.
#
# Aufruf:
#   powershell -ExecutionPolicy Bypass -File D:\Projekte\UltimateTracker\scripts\pull-manucloud-backups.ps1
#
# Zeitplan (täglich 04:30) – einmalig in einer **Administrator**-PowerShell:
#   schtasks /create /tn "UltimateTracker Backup-Abholung" /sc daily /st 04:30 ^
#     /tr "powershell -ExecutionPolicy Bypass -File D:\Projekte\UltimateTracker\scripts\pull-manucloud-backups.ps1"
#
# Voraussetzung: SSH-Alias `manucloud` in ~/.ssh/config (Schlüssel-Anmeldung).

$ErrorActionPreference = "Stop"

$SshHost   = "manucloud"                    # Alias aus ~/.ssh/config
$RemoteDir = "UltimateTracker/backups/"     # Pfad auf der Maschine
$TargetDir = "D:\Backups\manucloud"         # Ziel auf diesem Rechner
$KeepDays  = 60                             # Aufbewahrung der zweiten Kopie

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
$Log = Join-Path $TargetDir "pull.log"
$Stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# In das Zielverzeichnis wechseln und "." als Ziel angeben: sonst deutet scp
# den Doppelpunkt von "D:\..." als Rechnernamen.
Push-Location $TargetDir
try {
    $output = & scp -q -o BatchMode=yes "${SshHost}:${RemoteDir}*" . 2>&1
    if ($LASTEXITCODE -ne 0) { throw "scp fehlgeschlagen (Exit $LASTEXITCODE): $output" }

    $files = Get-ChildItem -File | Where-Object { $_.Name -ne "pull.log" }
    $newest = $files | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Add-Content $Log "$Stamp  OK  $($files.Count) Dateien, neueste: $($newest.Name)"

    Get-ChildItem -File |
        Where-Object { $_.Name -ne "pull.log" -and $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
} catch {
    Add-Content $Log "$Stamp  FEHLER  $_"
    Write-Error $_
    exit 1
} finally {
    Pop-Location
}
