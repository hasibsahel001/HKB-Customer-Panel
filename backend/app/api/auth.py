import threading
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import serialize_me, serialize_user
from app.auth.deps import AuthContext, client_ip, current_auth, require_csrf
from app.auth.permissions import Role
from app.auth.ratelimit import login_limiter
from app.core.config import settings
from app.core.errors import InvalidInput
from app.db import get_db
from app.models import User, UserSession, utcnow
from app.security import (
    burn_verify,
    hash_password,
    needs_rehash,
    new_token,
    token_hash,
    validate_password,
    validate_username,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["auth"])

_setup_lock = threading.Lock()
THEMES = {"light", "dark", "system"}


class SetupBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    password_confirm: str = Field(max_length=256)


class LoginBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class ChangePasswordBody(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class ProfileBody(BaseModel):
    theme: str | None = Field(default=None, max_length=16)


def _user_count(db: Session) -> int:
    return db.scalar(select(func.count(User.id))) or 0


def _too_many_attempts():
    return HTTPException(
        status_code=429,
        detail={
            "code": "too_many_attempts",
            "message": "Too many failed attempts. Try again later.",
        },
    )


@router.get("/setup/status")
def setup_status(db: Session = Depends(get_db)):
    return {"needs_setup": _user_count(db) == 0}


@router.post("/setup", status_code=201)
def setup(body: SetupBody, request: Request, db: Session = Depends(get_db)):
    username = validate_username(body.username)
    if body.password != body.password_confirm:
        raise InvalidInput("The passwords do not match")
    validate_password(body.password, username)

    with _setup_lock:
        if _user_count(db) > 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "setup_already_done",
                    "message": "Initial setup has already been completed",
                },
            )
        user = User(
            username=username,
            password_hash=hash_password(body.password),
            role=Role.SUPER_ADMIN.value,
        )
        db.add(user)
        db.commit()

    audit.record(db, "setup.super_admin_created", user=user, ip=client_ip(request))
    return serialize_user(user)


@router.post("/auth/login")
def login(
    body: LoginBody,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ip = client_ip(request) or "unknown"
    username = body.username.strip().lower()[:64]
    ip_key = f"ip:{ip}"
    user_key = f"user:{username}"

    if login_limiter.blocked(
        ip_key, settings.login_ip_max_attempts, settings.login_ip_window_seconds
    ) or login_limiter.blocked(
        user_key, settings.login_max_failures, settings.login_lockout_minutes * 60
    ):
        audit.record(db, "auth.login_blocked", username=username, ip=ip, success=False)
        raise _too_many_attempts()

    user = db.scalar(select(User).where(User.username == username))
    valid = False
    if user is not None and user.is_active:
        valid = verify_password(user.password_hash, body.password)
    else:
        burn_verify(body.password)

    if not valid:
        login_limiter.record(ip_key)
        login_limiter.record(user_key)
        audit.record(db, "auth.login_failed", username=username, ip=ip, success=False)
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_credentials", "message": "Invalid username or password"},
        )

    login_limiter.reset(user_key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)

    now = utcnow()
    db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now)
    )
    token = new_token()
    csrf = new_token()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=token_hash(token),
            csrf_token=csrf,
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.session_absolute_hours),
            ip=ip,
            user_agent=(request.headers.get("user-agent") or "")[:200],
        )
    )
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )
    audit.record(db, "auth.login", user=user, ip=ip)
    return serialize_me(user, csrf)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    db.delete(auth.session)
    db.commit()
    response.delete_cookie(settings.session_cookie_name, path="/")
    audit.record(db, "auth.logout", user=auth.user, ip=client_ip(request))
    return {"status": "ok"}


@router.get("/auth/me")
def me(auth: AuthContext = Depends(current_auth)):
    return serialize_me(auth.user, auth.session.csrf_token)


@router.patch("/auth/me")
def update_profile(
    body: ProfileBody,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if body.theme is not None:
        if body.theme not in THEMES:
            raise InvalidInput("The theme must be light, dark or system")
        auth.user.theme = body.theme
        db.commit()
    return serialize_me(auth.user, auth.session.csrf_token)


@router.post("/auth/change-password")
def change_password(
    body: ChangePasswordBody,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    user = auth.user
    ip = client_ip(request)
    user_key = f"user:{user.username}"

    if login_limiter.blocked(
        user_key, settings.login_max_failures, settings.login_lockout_minutes * 60
    ):
        raise _too_many_attempts()

    if not verify_password(user.password_hash, body.current_password):
        login_limiter.record(user_key)
        audit.record(db, "auth.password_change_failed", user=user, ip=ip, success=False)
        raise HTTPException(
            status_code=400,
            detail={
                "code": "wrong_current_password",
                "message": "The current password is not correct",
            },
        )

    if body.new_password == body.current_password:
        raise InvalidInput("The new password must differ from the current one")
    validate_password(body.new_password, user.username)

    user.password_hash = hash_password(body.new_password)
    db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id, UserSession.id != auth.session.id
        )
    )
    db.commit()
    audit.record(db, "auth.password_changed", user=user, ip=ip)
    return {"status": "ok"}


@router.get("/auth/sessions")
def list_sessions(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == auth.user.id)
        .order_by(UserSession.id.desc())
    ).all()
    return [
        {
            "id": s.id,
            "created_at": s.created_at.isoformat(),
            "last_seen_at": s.last_seen_at.isoformat(),
            "expires_at": s.expires_at.isoformat(),
            "ip": s.ip,
            "user_agent": s.user_agent,
            "current": s.id == auth.session.id,
        }
        for s in rows
    ]


@router.delete("/auth/sessions/{session_id}")
def revoke_session(
    session_id: int,
    request: Request,
    auth: AuthContext = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    target = db.get(UserSession, session_id)
    if target is None or target.user_id != auth.user.id:
        raise HTTPException(
            status_code=404,
            detail={"code": "session_not_found", "message": "Session not found"},
        )
    db.delete(target)
    db.commit()
    audit.record(
        db, "auth.session_revoked", user=auth.user, ip=client_ip(request), target=str(session_id)
    )
    return {"status": "ok"}