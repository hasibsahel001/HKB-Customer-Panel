from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import RecentCheck, User, utcnow

KEEP_DAYS = 7


def record_recent(db: Session, user: User, report: dict) -> None:
    sections = report.get("sections") or {}
    pppoe = (sections.get("pppoe") or {}).get("data") or {}
    identity = (sections.get("identity") or {}).get("data") or {}
    overall = (report.get("diagnostics") or {}).get("overall")

    ip = str(report.get("ip") or "")[:64]
    tid = str(report.get("technical_id") or "")[:32]
    username = pppoe.get("username")
    row = db.scalar(
        select(RecentCheck).where(
            RecentCheck.user_id == user.id, RecentCheck.ip == ip, RecentCheck.tid == tid
        )
    )
    if row is None:
        row = RecentCheck(user_id=user.id, ip=ip, tid=tid)
        db.add(row)
    row.pppoe_username = str(username)[:128] if username else row.pppoe_username
    row.identity = str(identity.get("identity"))[:128] if identity.get("identity") else row.identity
    row.overall = overall
    row.checked_at = utcnow()

    db.execute(
        delete(RecentCheck).where(
            RecentCheck.user_id == user.id,
            RecentCheck.checked_at < utcnow() - timedelta(days=KEEP_DAYS),
        )
    )
    db.commit()


def list_recent(db: Session, user: User, query: str = "", limit: int = 100) -> list[dict]:
    since = utcnow() - timedelta(hours=settings.recent_hours)
    found = db.scalars(
        select(RecentCheck)
        .where(RecentCheck.user_id == user.id, RecentCheck.checked_at >= since)
        .order_by(RecentCheck.checked_at.desc())
        .limit(500)
    ).all()

    needle = query.strip().lower()
    items, seen = [], set()
    for row in found:
        key = row.pppoe_username or f"ip:{row.ip}"
        if key in seen:
            continue
        if needle and not any(
            needle in (value or "").lower()
            for value in (row.pppoe_username, row.ip, row.tid, row.identity)
        ):
            continue
        seen.add(key)
        items.append(
            {
                "username": row.pppoe_username,
                "ip": row.ip,
                "tid": row.tid,
                "identity": row.identity,
                "overall": row.overall,
                "checked_at": row.checked_at.isoformat(),
            }
        )
        if len(items) >= limit:
            break
    return items