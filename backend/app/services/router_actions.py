import ipaddress
import re
import time

from librouteros import exceptions as ros_exc

from app.core.errors import InvalidInput
from app.services.network_parsing import parse_rate_pair, queue_matches
from app.services.parsing import to_bool

DELETE_ALL_PHRASE = "DELETE ALL"
MAX_TARGETS = 60
UPDATE_CHANNEL = "stable"

_RATE_RE = re.compile(r"^(\d+(?:\.\d+)?)([kKmMgG]?)$")
_ID_RE = re.compile(r"^\*[0-9A-Fa-f]+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?")

_CLOSED = (
    ros_exc.FatalError,
    getattr(ros_exc, "ConnectionClosed", ros_exc.FatalError),
    OSError,
    EOFError,
)


class RouterCommandFailed(Exception):
    """The router refused a command (for example because the account lacks permission)."""


def _command(api, cmd, *words):
    try:
        return list(api.rawCmd(cmd, *words))
    except ros_exc.TrapError as exc:
        raise RouterCommandFailed(str(exc)[:200]) from exc


# ---------------------------------------------------------------- queues


def normalize_rate(text) -> str:
    value = str(text if text is not None else "").strip()
    match = _RATE_RE.match(value)
    if not match:
        raise InvalidInput("A speed must look like 512k, 10M or 1G (use 0 for unlimited)")
    number, unit = match.group(1), match.group(2)
    if float(number) == 0:
        return "0"
    unit = unit.lower()
    return number + ("k" if unit == "k" else unit.upper())


def bps_to_text(bps) -> str:
    if bps is None:
        return "0"
    if bps % 1_000_000 == 0:
        return f"{bps // 1_000_000}M"
    if bps % 1_000 == 0:
        return f"{bps // 1_000}k"
    return str(bps)


def normalize_target(text) -> str:
    value = str(text if text is not None else "").strip()
    if not value:
        raise InvalidInput("A target is empty")
    try:
        network = ipaddress.ip_network(value if "/" in value else f"{value}/32", strict=True)
    except ValueError:
        raise InvalidInput(f"'{value}' is not a valid IPv4 address or network")
    if network.version != 4:
        raise InvalidInput("Only IPv4 targets are supported")
    if network.prefixlen == 0:
        raise InvalidInput("A catch-all target (/0) is not allowed")
    return str(network)


def normalize_targets(values) -> list:
    result = []
    for value in values or []:
        target = normalize_target(value)
        if target not in result:
            result.append(target)
    if not result:
        raise InvalidInput("At least one target is required")
    if len(result) > MAX_TARGETS:
        raise InvalidInput(f"A queue can have at most {MAX_TARGETS} targets")
    return result


def validate_name(text) -> str:
    value = str(text if text is not None else "").strip()
    if not value or len(value) > 64 or _CONTROL_RE.search(value):
        raise InvalidInput("The queue name must be 1 to 64 printable characters")
    return value


def validate_ids(ids) -> list:
    cleaned = [str(i).strip() for i in ids or []]
    if not cleaned or any(not _ID_RE.match(i) for i in cleaned):
        raise InvalidInput("Invalid queue id")
    return cleaned


def queue_view(row, customer_ips) -> dict:
    targets = [t.strip() for t in str(row.get("target") or "").split(",") if t.strip()]
    up, down = parse_rate_pair(row.get("max-limit"))
    return {
        "id": row.get(".id"),
        "name": row.get("name"),
        "targets": targets,
        "max_up_bps": up,
        "max_down_bps": down,
        "max_up": bps_to_text(up),
        "max_down": bps_to_text(down),
        "disabled": bool(to_bool(row.get("disabled"))),
        "parent": row.get("parent"),
        "comment": row.get("comment") or None,
        "matches_customer": bool(queue_matches(row.get("target"), customer_ips)),
    }


def list_all_queues(api, customer_ips) -> list:
    """Every simple queue on the router, without exception."""
    return [queue_view(row, customer_ips) for row in api.path("queue", "simple")]


def save_queue(api, *, queue_id, name, targets, max_up, max_down, disabled) -> str:
    fields = {
        "name": validate_name(name),
        "target": ",".join(normalize_targets(targets)),
        "max-limit": f"{normalize_rate(max_up)}/{normalize_rate(max_down)}",
        "disabled": "yes" if disabled else "no",
    }
    path = api.path("queue", "simple")
    if queue_id:
        if not _ID_RE.match(str(queue_id)):
            raise InvalidInput("Invalid queue id")
        if not any(row.get(".id") == queue_id for row in path):
            raise InvalidInput("The queue no longer exists; reload the list")
        path.update(**{".id": queue_id}, **fields)
        return queue_id
    return path.add(**fields)


def delete_queues(api, ids) -> int:
    cleaned = validate_ids(ids)
    api.path("queue", "simple").remove(*cleaned)
    return len(cleaned)


def delete_all_queues(api) -> int:
    path = api.path("queue", "simple")
    ids = [row.get(".id") for row in path if row.get(".id")]
    if ids:
        path.remove(*ids)
    return len(ids)


# ---------------------------------------------------------------- reboot


def send_reboot(api) -> None:
    try:
        list(api.rawCmd("/system/reboot"))
    except _CLOSED:
        pass


# ---------------------------------------------------------------- RouterOS update


def parse_version(text):
    match = _VERSION_RE.match(str(text or ""))
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def _is_error(status: str) -> bool:
    text = status.lower()
    return text.startswith("error") or any(
        word in text for word in ("could not", "cannot", "can't", "failed")
    )


def read_update_state(api) -> dict:
    rows = list(api.path("system", "package", "update"))
    row = rows[0] if rows else {}
    return {
        "channel": row.get("channel"),
        "installed": row.get("installed-version"),
        "latest": row.get("latest-version"),
        "status": row.get("status"),
    }


def classify_update(state) -> str:
    status = str(state.get("status") or "")
    if _is_error(status):
        return "error"
    installed = parse_version(state.get("installed"))
    latest = parse_version(state.get("latest"))
    if installed is None or latest is None:
        return "unknown"
    if installed[0] != latest[0]:
        return "major_change"
    return "available" if latest > installed else "up_to_date"


def firmware_info(api) -> dict:
    empty = {"supported": False, "model": None, "current": None, "upgrade": None, "pending": False}
    try:
        rows = list(api.path("system", "routerboard"))
    except Exception:
        return empty
    row = rows[0] if rows else {}
    if not to_bool(row.get("routerboard")):
        return empty
    current, upgrade = row.get("current-firmware"), row.get("upgrade-firmware")
    pending = False
    if current and upgrade:
        a, b = parse_version(current), parse_version(upgrade)
        pending = (b > a) if a and b else str(current) != str(upgrade)
    return {
        "supported": True,
        "model": row.get("model"),
        "current": current,
        "upgrade": upgrade,
        "pending": pending,
    }


def check_updates(api) -> dict:
    before = read_update_state(api)
    changed_from = None
    if str(before.get("channel") or "").lower() != UPDATE_CHANNEL:
        changed_from = before.get("channel")
        _command(api, "/system/package/update/set", f"=channel={UPDATE_CHANNEL}")
    _command(api, "/system/package/update/check-for-updates")
    state = read_update_state(api)
    return {
        **state,
        "state": classify_update(state),
        "channel_changed_from": changed_from,
        "firmware": firmware_info(api),
    }


def download_update(api, sleep=time.sleep, polls=60, interval=5.0) -> dict:
    _command(api, "/system/package/update/download")
    for _ in range(polls):
        state = read_update_state(api)
        status = str(state.get("status") or "")
        if "downloaded" in status.lower():
            return state
        if _is_error(status):
            raise RouterCommandFailed(f"The download failed: {status[:150]}")
        sleep(interval)
    raise RouterCommandFailed("The download did not finish in time")


def enable_auto_firmware(api) -> bool:
    try:
        _command(api, "/system/routerboard/settings/set", "=auto-upgrade=yes")
        return True
    except Exception:
        return False


def upgrade_firmware(api) -> dict:
    info = firmware_info(api)
    if not info["supported"]:
        raise InvalidInput("This device has no Routerboard firmware to upgrade")
    if not info["pending"]:
        raise InvalidInput("The firmware is already up to date")
    _command(api, "/system/routerboard/upgrade")
    return info


# ---------------------------------------------------------------- customer AP access (NAT / local VPN)

NAT_PORT = 90
NAT_TARGET_PORT = 80
PPTP_SECRET_NAME = "1"
PPTP_SECRET_PASSWORD = "1"
PPTP_PROFILE = "*0"
PPTP_LOCAL_ADDRESS = "1.1.1.23"
PPTP_REMOTE_ADDRESS = "1.1.1.25"


def find_customer_ap_ip(api, candidates) -> str | None:
    for raw in candidates:
        try:
            ipaddress.ip_address(raw)
        except ValueError:
            continue
        try:
            rows = _command(api, "/ping", f"=address={raw}", "=interface=ether1", "=count=1")
        except RouterCommandFailed:
            continue
        if rows and str(rows[-1].get("received") or "0") not in ("0", ""):
            return raw
    return None


def _is_ap_forward(row) -> bool:
    """A dst-nat rule that sends TCP port 90 somewhere (to any address, not only to this AP)."""
    return (
        row.get("chain") == "dstnat"
        and row.get("protocol") == "tcp"
        and str(row.get("dst-port")) == str(NAT_PORT)
        and row.get("action") == "dst-nat"
    )


def ensure_nat_rule(api, ap_ip: str) -> str:
    """Makes port 90 lead to `ap_ip` and puts that rule first in the NAT table.

    NAT rules are read from the top, so a port-90 rule that already exists for another address
    would win over a new rule added below it. So an existing port-90 rule is edited to point to
    this AP (and moved to the top) instead of adding a second one.

    Returns "added", "updated" (an existing rule was edited), "moved" (only moved to the top) or
    "unchanged".
    """
    path = api.path("ip", "firewall", "nat")
    table = list(path)
    first_id = table[0].get(".id") if table else None
    existing = [row for row in table if _is_ap_forward(row)]

    if not existing:
        rule_id = path.add(
            chain="dstnat",
            protocol="tcp",
            **{"dst-port": str(NAT_PORT), "action": "dst-nat", "to-addresses": ap_ip, "to-ports": str(NAT_TARGET_PORT)},
        )
        state = "added"
    else:
        rule = existing[0]  # the first one is the rule the router actually uses
        rule_id = rule[".id"]
        changes = {}
        if rule.get("to-addresses") != ap_ip:
            changes["to-addresses"] = ap_ip
        if str(rule.get("to-ports")) != str(NAT_TARGET_PORT):
            changes["to-ports"] = str(NAT_TARGET_PORT)
        if to_bool(rule.get("disabled")):
            changes["disabled"] = "no"
        if changes:
            path.update(**{".id": rule_id}, **changes)
            state = "updated"
        else:
            state = "unchanged"

    if first_id is not None and rule_id != first_id:
        _command(api, "/ip/firewall/nat/move", f"=numbers={rule_id}", f"=destination={first_id}")
        if state == "unchanged":
            state = "moved"
    return state


def _secret_matches(row) -> bool:
    return (
        row.get("password") == PPTP_SECRET_PASSWORD
        and row.get("profile") == PPTP_PROFILE
        and row.get("local-address") == PPTP_LOCAL_ADDRESS
        and row.get("remote-address") == PPTP_REMOTE_ADDRESS
        and row.get("service") == "any"
    )


def _find_secret_rows(api):
    return [row for row in api.path("ppp", "secret") if str(row.get("name") or "").strip() == PPTP_SECRET_NAME]


def ensure_pptp_access(api) -> bool:
    _command(
        api,
        "/interface/pptp-server/server/set",
        "=enabled=yes",
        "=authentication=pap,chap,mschap1,mschap2",
    )
    secrets = api.path("ppp", "secret")
    fields = {
        "password": PPTP_SECRET_PASSWORD,
        "profile": PPTP_PROFILE,
        "local-address": PPTP_LOCAL_ADDRESS,
        "remote-address": PPTP_REMOTE_ADDRESS,
        "service": "any",
    }

    existing = _find_secret_rows(api)
    if existing:
        changed = False
        if not _secret_matches(existing[0]):
            secrets.update(**{".id": existing[0][".id"]}, **fields)
            changed = True
        if len(existing) > 1:
            secrets.remove(*[row[".id"] for row in existing[1:]])
            changed = True
        return changed

    try:
        secrets.add(name=PPTP_SECRET_NAME, **fields)
        return True
    except ros_exc.TrapError as exc:
        if "already exists" not in str(exc).lower():
            raise RouterCommandFailed(str(exc)[:200]) from exc
        stale = _find_secret_rows(api)
        if stale:
            secrets.remove(*[row[".id"] for row in stale])
        try:
            secrets.add(name=PPTP_SECRET_NAME, **fields)
        except ros_exc.TrapError as exc2:
            raise RouterCommandFailed(str(exc2)[:200]) from exc2
        return True


# ---------------------------------------------------------------- DNS settings


def read_dns(api) -> dict:
    rows = list(api.path("ip", "dns"))
    row = rows[0] if rows else {}
    servers = [s.strip() for s in str(row.get("servers") or "").split(",") if s.strip()]
    dynamic = [s.strip() for s in str(row.get("dynamic-servers") or "").split(",") if s.strip()]
    return {
        "servers": servers,
        "dynamic_servers": dynamic,
        "allow_remote_requests": bool(to_bool(row.get("allow-remote-requests"))),
    }


def _validate_dns_server(value: str) -> str:
    value = value.strip()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        raise InvalidInput(f"'{value}' is not a valid DNS server address")
    return value


def save_dns(api, servers: list, allow_remote_requests: bool) -> dict:
    cleaned = [_validate_dns_server(s) for s in servers if str(s).strip()]
    if len(cleaned) > 4:
        raise InvalidInput("At most 4 DNS servers are supported here")
    api.path("ip", "dns").update(
        servers=",".join(cleaned),
        **{"allow-remote-requests": "yes" if allow_remote_requests else "no"},
    )
    return read_dns(api)