from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import audit
from app.auth.deps import AuthContext, client_ip, require_permission
from app.auth.permissions import Permission, can_manage_role
from app.db import get_db
from app.models import AuditLog, RecentCheck, User, UserSession, utcnow

router = APIRouter(prefix="/api", tags=["maintenance"])


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail={"code": "user_not_found", "message": "User not found"})
    if target.id == auth.user.id:
        raise HTTPException(
            status_code=400,
            detail={"code": "cannot_modify_self", "message": "You cannot delete your own account"},
        )
    if not can_manage_role(auth.user.role, target.role):
        raise HTTPException(
            status_code=403,
            detail={"code": "role_not_allowed", "message": "You are not allowed to delete this user"},
        )

    username, role = target.username, target.role
    db.execute(delete(UserSession).where(UserSession.user_id == target.id))
    db.execute(delete(RecentCheck).where(RecentCheck.user_id == target.id))
    db.delete(target)
    db.commit()
    audit.record(
        db, "users.deleted", user=auth.user, ip=client_ip(request), target=username, details={"role": role}
    )
    return {"status": "ok"}


@router.delete("/audit")
def clear_audit(
    request: Request,
    older_than_days: int | None = Query(default=None, ge=0, le=3650),
    auth: AuthContext = Depends(require_permission(Permission.AUDIT_DELETE)),
    db: Session = Depends(get_db),
):
    statement = delete(AuditLog)
    if older_than_days is not None:
        statement = statement.where(AuditLog.created_at < utcnow() - timedelta(days=older_than_days))
    deleted = db.execute(statement).rowcount or 0
    db.commit()
    # The deletion itself is recorded after it, so it can never be erased silently.
    audit.record(
        db,
        "audit.cleared",
        user=auth.user,
        ip=client_ip(request),
        details={"deleted": deleted, "older_than_days": older_than_days},
    )
    return {"deleted": deleted}


@router.delete("/customer/recent/mine")
def clear_my_recent(
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.CUSTOMER_CHECK)),
    db: Session = Depends(get_db),
):
    deleted = db.execute(delete(RecentCheck).where(RecentCheck.user_id == auth.user.id)).rowcount or 0
    db.commit()
    audit.record(db, "recent.cleared_mine", user=auth.user, ip=client_ip(request), details={"deleted": deleted})
    return {"deleted": deleted}


@router.delete("/customer/recent/all")
def clear_all_recent(
    request: Request,
    auth: AuthContext = Depends(require_permission(Permission.USERS_MANAGE)),
    db: Session = Depends(get_db),
):
    deleted = db.execute(delete(RecentCheck)).rowcount or 0
    db.commit()
    audit.record(db, "recent.cleared_all", user=auth.user, ip=client_ip(request), details={"deleted": deleted})
    return {"deleted": deleted}