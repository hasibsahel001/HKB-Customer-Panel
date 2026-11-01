"""Creates or updates the Windows PPTP VPN entry used to reach a customer's access point.

This only works when the panel runs on the Windows PC of the person using it (run-panel.bat): the
entry is created for the user the panel runs as, with the built-in Add-VpnConnection command.
On any other system nothing is done and the panel says so.

Every value that reaches PowerShell is checked first and passed through environment variables, so
nothing from a request is ever put into a command line.
"""

import ipaddress
import logging
import os
import re
import subprocess
import sys

from app.core.config import settings
from app.core.errors import InvalidInput

log = logging.getLogger("hkb.windows_vpn")

VPN_USER = "1"
VPN_PASSWORD = "1"
TIMEOUT_SECONDS = 60
_NAME_RE = re.compile(r"^[A-Za-z0-9 _.-]{1,40}$")


class VpnSetupFailed(Exception):
    """PowerShell could not create or update the VPN entry."""


# One entry named VPN is reused for every customer: only its server address and the route to the
# customer's access point change. Split tunnelling keeps the PC's own internet off the VPN.
SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$n = $env:HKB_VPN_NAME
$server = $env:HKB_VPN_SERVER
$ap = $env:HKB_VPN_AP
$all = $env:HKB_VPN_ALL_AP -split ','
$existing = Get-VpnConnection -Name $n -ErrorAction SilentlyContinue
if ($existing) {
  if ($existing.ConnectionStatus -eq 'Connected') {
    rasdial $n /disconnect | Out-Null
    Start-Sleep -Seconds 1
  }
  Set-VpnConnection -Name $n -ServerAddress $server -TunnelType Pptp -AuthenticationMethod MSChapv2 -SplitTunneling $true -RememberCredential $true -Force
  Write-Output 'STATE=updated'
} else {
  Add-VpnConnection -Name $n -ServerAddress $server -TunnelType Pptp -AuthenticationMethod MSChapv2 -EncryptionLevel Optional -SplitTunneling -RememberCredential -Force
  Write-Output 'STATE=created'
}
# Old routes: a missing one is normal, so every failure here is ignored.
foreach ($a in $all) {
  try { Remove-VpnConnectionRoute -ConnectionName $n -DestinationPrefix "$a/32" -ErrorAction Stop | Out-Null } catch { }
}
try { Add-VpnConnectionRoute -ConnectionName $n -DestinationPrefix "$ap/32" -ErrorAction Stop | Out-Null } catch { }

# Save the user name and password inside the connection (Add-VpnConnection cannot), so only
# the Connect button is left to press.
try {
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class HkbRas {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public struct RASCREDENTIALS {
    public int dwSize;
    public int dwMask;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 257)] public string szUserName;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 257)] public string szPassword;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 16)] public string szDomain;
  }
  [DllImport("rasapi32.dll", CharSet = CharSet.Unicode)]
  public static extern int RasSetCredentials(string phonebook, string entry, ref RASCREDENTIALS cred, bool clear);
  public static int Save(string phonebook, string entry, string user, string pass) {
    RASCREDENTIALS c = new RASCREDENTIALS();
    c.dwSize = Marshal.SizeOf(typeof(RASCREDENTIALS));
    c.dwMask = 3; // user name + password
    c.szUserName = user; c.szPassword = pass; c.szDomain = "";
    return RasSetCredentials(phonebook, entry, ref c, false);
  }
}
'@
  $pbk = Join-Path $env:APPDATA 'Microsoft\Network\Connections\Pbk\rasphone.pbk'
  $rc = [HkbRas]::Save($pbk, $n, $env:HKB_VPN_USER, $env:HKB_VPN_PASS)
  if ($rc -eq 0) { Write-Output 'CREDS=1' } else { Write-Output 'CREDS=0' }
} catch { Write-Output 'CREDS=0' }

if ($env:HKB_VPN_CONNECT -eq '1') {
  $out = rasdial $n $env:HKB_VPN_USER $env:HKB_VPN_PASS 2>&1 | Out-String
  if ($LASTEXITCODE -eq 0) {
    Write-Output 'CONNECTED=1'
  } else {
    Write-Output 'CONNECTED=0'
    Write-Output ('MESSAGE=' + ($out -replace '\s+', ' ').Trim())
  }
}
"""


def _parse(output: str) -> dict:
    found = {}
    for line in output.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key in {"STATE", "CONNECTED", "MESSAGE", "CREDS"}:
            found[key] = value
    return found


def apply_pptp(server_ip: str, ap_ip: str, *, connect: bool = True, runner=subprocess.run, platform=None) -> dict:
    """Points the Windows VPN entry at `server_ip` (the customer's PPPoE IP) and connects it."""
    if not (platform or sys.platform).startswith("win"):
        return {
            "supported": False,
            "message": "The panel does not run on Windows, so it cannot create a VPN entry. Create it by hand.",
        }

    name = settings.vpn_connection_name
    if not _NAME_RE.match(name):
        raise InvalidInput("The VPN name in the settings is not valid")
    try:
        server = str(ipaddress.IPv4Address(server_ip))
    except ValueError:
        raise InvalidInput("The PPPoE IP is not valid")
    if ap_ip not in settings.ap_probe_peers:
        raise InvalidInput("That access point address is not one of the known ones")

    env = {
        **os.environ,
        "HKB_VPN_NAME": name,
        "HKB_VPN_SERVER": server,
        "HKB_VPN_AP": ap_ip,
        "HKB_VPN_ALL_AP": ",".join(settings.ap_probe_peers),
        "HKB_VPN_CONNECT": "1" if connect else "0",
        "HKB_VPN_USER": VPN_USER,
        "HKB_VPN_PASS": VPN_PASSWORD,
    }
    try:
        proc = runner(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", SCRIPT],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise VpnSetupFailed("Windows took too long to set up the VPN")
    except OSError as exc:
        raise VpnSetupFailed(f"PowerShell could not be started: {type(exc).__name__}")

    if proc.returncode != 0:
        log.info("vpn setup failed: %s", (proc.stderr or "").strip()[:200])
        raise VpnSetupFailed((proc.stderr or proc.stdout or "PowerShell failed").strip()[:200])

    found = _parse(proc.stdout or "")
    return {
        "supported": True,
        "name": name,
        "server": server,
        "state": found.get("STATE", "updated"),
        "connected": (found.get("CONNECTED") == "1") if connect else None,
        "credentials_saved": found.get("CREDS") == "1",
        "message": found.get("MESSAGE") or None,
    }