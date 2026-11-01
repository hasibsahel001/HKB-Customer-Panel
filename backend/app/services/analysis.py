from enum import Enum

from app.core.config import settings


class Status(str, Enum):
    NORMAL = "normal"      # green
    WARNING = "warning"    # yellow
    SERIOUS = "serious"    # orange
    CRITICAL = "critical"  # red
    UNKNOWN = "unknown"    # gray


_RANK = {
    Status.UNKNOWN: 0,
    Status.NORMAL: 1,
    Status.WARNING: 2,
    Status.SERIOUS: 3,
    Status.CRITICAL: 4,
}


def classify_signal(dbm):
    if dbm is None:
        return Status.UNKNOWN
    if dbm >= settings.signal_normal_dbm:
        return Status.NORMAL
    if dbm >= settings.signal_warning_dbm:
        return Status.WARNING
    if dbm >= settings.signal_serious_dbm:
        return Status.SERIOUS
    return Status.CRITICAL


def classify_ccq(percent):
    if percent is None:
        return Status.UNKNOWN
    if percent >= settings.ccq_normal_percent:
        return Status.NORMAL
    if percent >= settings.ccq_serious_percent:
        return Status.WARNING
    if percent >= settings.ccq_critical_percent:
        return Status.SERIOUS
    return Status.CRITICAL


def worst_status(*statuses):
    """Return the most severe status; UNKNOWN only wins when nothing else is known."""
    return max(statuses, key=lambda s: _RANK[s])


def classify_chain(tx_dbm, rx_dbm):
    """A chain is as healthy as its worse direction."""
    return worst_status(classify_signal(tx_dbm), classify_signal(rx_dbm))