<#
.SYNOPSIS
  Macht die Ports der WSL-Distro im LAN erreichbar (Windows-Host als Brücke).

.DESCRIPTION
  WSL2 nutzt NAT: veröffentlichte Container-Ports sind nur auf "localhost"
  sichtbar, nicht von anderen Geräten (Handy!) im LAN. Dieses Skript richtet
  dafür eine Port-Weiterleitung auf dem Windows-Host ein (netsh portproxy) und
  öffnet die nötigen Firewall-Regeln.

  In einer PowerShell **als Administrator** ausführen:
      powershell -ExecutionPolicy Bypass -File scripts\windows-lan-forward.ps1

  Hinweis: Die WSL-IP ändert sich nach einem Neustart der Distro – Skript dann
  einfach erneut ausführen. Alternativen siehe docs/deployment.md (Abschnitt 8.3):
  "networkingMode=mirrored" in .wslconfig oder Tailscale direkt in der WSL.
#>

param(
    [string]$Distro = "UltimateTracker",
    [int[]]$Ports = @(8085, 8082, 4321, 80, 443)
)

$ErrorActionPreference = "Stop"

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Bitte in einer PowerShell als Administrator ausführen."
}

$wslIp = (wsl -d $Distro -- hostname -I).Trim().Split()[0]
if (-not $wslIp) { Write-Error "WSL-IP nicht ermittelbar – läuft die Distro '$Distro'?" }
Write-Host "WSL-IP ($Distro): $wslIp"

foreach ($port in $Ports) {
    netsh interface portproxy delete v4tov4 listenport=$port listenaddress=0.0.0.0 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenport=$port listenaddress=0.0.0.0 connectport=$port connectaddress=$wslIp | Out-Null
    if (-not (Get-NetFirewallRule -DisplayName "UltimateTracker $port" -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName "UltimateTracker $port" -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $port -Profile Private | Out-Null
    }
    Write-Host ("  {0,5} -> {1}" -f $port, $wslIp)
}

Write-Host "`nAktuelle Weiterleitungen:"
netsh interface portproxy show v4tov4

Write-Host "`nTest vom Handy: http://<Host-IP>:8085  (Host-IP steht oben in ipconfig)"
Write-Host "Danach ggf. noch die Firewall-Freigabe für das private Profil prüfen."
