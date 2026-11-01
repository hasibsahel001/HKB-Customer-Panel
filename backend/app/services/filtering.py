import ipaddress

from app.core.config import settings

# Findings that are intentionally not shown. Remove a code from this set to show it again.
HIDDEN_FINDING_CODES = frozenset(
    {
        "queue_very_low_limit",
        "queue_overlap",
        "queue_near_limit",
        "dhcp_ip_conflict",
    }
)


def overall_of(findings) -> str:
    """Worst severity of the findings; informational ('normal') findings never change it."""
    levels = {f.get("severity") for f in findings}
    for level in ("critical", "serious", "warning"):
        if level in levels:
            return level
    return "unknown" if levels - {"normal"} else "normal"


def hide_findings(diagnostics, hidden=HIDDEN_FINDING_CODES):
    """Remove hidden findings and recompute the count and the overall status."""
    if not isinstance(diagnostics, dict) or not isinstance(diagnostics.get("findings"), list):
        return diagnostics
    kept = [f for f in diagnostics["findings"] if f.get("code") not in hidden]
    if len(kept) == len(diagnostics["findings"]):
        return diagnostics
    diagnostics["findings"] = kept
    diagnostics["count"] = len(kept)
    diagnostics["overall"] = overall_of(kept)
    return diagnostics


def _infrastructure_ips() -> set:
    ips = set()
    for raw in settings.ap_probe_peers:
        try:
            ips.add(str(ipaddress.ip_address(str(raw).strip())))
        except ValueError:
            continue
    return ips


def drop_infrastructure_devices(report):
    """The customer's own access point is not a phone or a computer, so it is not listed as a device."""
    section = (report.get("sections") or {}).get("devices")
    data = section.get("data") if isinstance(section, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        return report
    ips = _infrastructure_ips()
    kept = [d for d in data["devices"] if d.get("ip") not in ips]
    if len(kept) != len(data["devices"]):
        data["devices"] = kept
        data["count"] = len(kept)
    return report