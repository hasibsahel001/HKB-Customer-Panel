import ipaddress
import re

from app.core.config import settings
from app.core.errors import InvalidInput

_TID_RE = re.compile(r"^\d{1,12}$")


def validate_tid(tid: str) -> str:
    tid = (tid or "").strip()
    if not _TID_RE.match(tid):
        raise InvalidInput("Technical ID must contain digits only")
    return tid


def validate_target_ip(raw: str) -> str:
    try:
        ip = ipaddress.ip_address((raw or "").strip())
    except ValueError:
        raise InvalidInput("The IP address is not valid")
    if ip.version != 4:
        raise InvalidInput("Only IPv4 is supported")
    if ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_link_local:
        raise InvalidInput("This address is not allowed")
    nets = [ipaddress.ip_network(n) for n in settings.allowed_networks]
    if not any(ip in n for n in nets):
        raise InvalidInput("The address is outside the allowed management ranges")
    return str(ip)