from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import AuthContext, require_permission
from app.auth.permissions import Permission
from app.db import get_db
from app.models import AuditLog

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: str | None = Query(default=None, max_length=64),
    auth: AuthContext = Depends(require_permission(Permission.AUDIT_VIEW)),
    db: Session = Depends(get_db),
):
    query = select(AuditLog)
    count_query = select(func.count(AuditLog.id))
    if action:
        query = query.where(AuditLog.action == action)
        count_query = count_query.where(AuditLog.action == action)

    rows = db.scalars(
        query.order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "total": db.scalar(count_query) or 0,
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "user_id": r.user_id,
                "username": r.username,
                "action": r.action,
                "target": r.target,
                "ip": r.ip,
                "success": r.success,
                "details": r.details,
            }
            for r in rows
        ],
    }