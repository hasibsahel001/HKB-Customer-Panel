import re

from app.core.config import settings
from app.services.analysis import Status, worst_status
from app.services.parsing import leading_number

_RTT_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|us|s)")
_TO_MS = {"s": 1000.0, "ms": 1.0, "us": 0.001}


def parse_rtt_ms(value):
    """Convert RouterOS times like '12ms', '1ms500us', '800us' to milliseconds."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "")
    parts = _RTT_PART.findall(text)
    if not parts:
        return None
    if "".join(number + unit for number, unit in parts) != text:
        return None
    return sum(float(number) * _TO_MS[unit] for number, unit in parts)


def summarize_ping(rows):
    """Summarize the streamed rows of a RouterOS ping. The last row holds the totals."""
    rows = [r for r in rows if r]
    if not rows:
        return None
    last = rows[-1]

    sent = leading_number(last.get("sent"))
    received = leading_number(last.get("received"))
    loss = leading_number(last.get("packet-loss"))
    if loss is None and sent and received is not None:
        loss = round((sent - received) * 100 / sent, 1)

    avg = parse_rtt_ms(last.get("avg-rtt"))
    if avg is None:
        times = [parse_rtt_ms(r.get("time")) for r in rows]
        times = [t for t in times if t is not None]
        avg = round(sum(times) / len(times), 2) if times else None

    return {
        "sent": int(sent) if sent is not None else None,
        "received": int(received) if received is not None else None,
        "loss_percent": loss,
        "min_ms": parse_rtt_ms(last.get("min-rtt")),
        "avg_ms": avg,
        "max_ms": parse_rtt_ms(last.get("max-rtt")),
        "reachable": (received > 0) if received is not None else None,
    }


def _classify_loss(loss):
    if loss is None:
        return Status.UNKNOWN
    if loss >= settings.ping_loss_serious_percent:
        return Status.SERIOUS
    if loss >= settings.ping_loss_warning_percent:
        return Status.WARNING
    return Status.NORMAL


def _classify_latency(avg_ms):
    if avg_ms is None:
        return Status.UNKNOWN
    if avg_ms >= settings.ping_latency_serious_ms:
        return Status.SERIOUS
    if avg_ms >= settings.ping_latency_warning_ms:
        return Status.WARNING
    return Status.NORMAL


def classify_ping(summary):
    if summary is None or summary.get("reachable") is None:
        return Status.UNKNOWN
    if summary["reachable"] is False:
        return Status.CRITICAL
    return worst_status(
        _classify_loss(summary.get("loss_percent")),
        _classify_latency(summary.get("avg_ms")),
    )