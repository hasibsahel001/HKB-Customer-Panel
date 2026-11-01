from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.api.serializers import serialize_user
from app.auth.deps import AuthContext, client_ip, require_permission
from app.auth.permissions import Permission, Role, can_assign_role, can_manage_role
from app.core.errors import InvalidInput
from app.db import get_db
from app.models import User, UserSession
from app.security import hash_password, validate_password, validate_username

router = APIRouter(prefix="/api/users", tags=["users"])

manage_users = require_permission(Permission.USERS_MANAGE)


class CreateUserBody(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)
    role: str = Field(max_length=32)


class UpdateUserBody(BaseModel):
    role: str | None = Field(default=None, max_length=32)
    is_active: bool | None = None


class ResetPasswordBody(BaseModel):
    new_password: str = Field(max_length=256)


def _forbidden(message="You are not allowed to manage this user or role"):
    return HTTPException(status_code=403, detail={"code": "role_not_allowed", "message": message})


def _parse_role(value: str) -> Role:
    try:
        return Role(value)
    except ValueError:
        raise InvalidInput("Unknown role")


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=404, detail={"code": "user_not_found", "message": "User not found"}
        )
    return user


def _revoke_sessions(db: Session, user_id: int) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))


@router.get("")
def list_users(auth: AuthContext = Depends(manage_users), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.id)).all()
    return [serialize_user(u) for u in users]


@router.post("", status_code=201)
def create_user(
    body: CreateUserBody,
    request: Request,
    auth: AuthContext = Depends(manage_users),
    db: Session = Depends(get_db),
):
    role = _parse_role(body.role)
    if not can_assign_role(auth.user.role, role):
        raise _forbidden()

    username = validate_username(body.username)
    validate_password(body.password, username)

    if db.scalar(select(User).where(User.username == username)) is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "username_taken", "message": "This username is already in use"},
        )

    user = User(
        username=username,
        password_hash=hash_password(body.password),
        role=role.value,
    )
    db.add(user)
    db.commit()
    audit.record(
        db,
        "users.created",
        user=auth.user,
        ip=client_ip(request),
        target=username,
        details={"role": role.value},
    )
    return serialize_user(user)


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    body: UpdateUserBody,
    request: Request,
    auth: AuthContext = Depends(manage_users),
    db: Session = Depends(get_db),
):
    target = _get_user(db, user_id)

    # A user can never edit themselves, so at least one active Super Admin always remains:
    # a Super Admin can only be edited by another active Super Admin.
    if target.id == auth.user.id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "cannot_modify_self",
                "message": "You cannot change your own role or status",
            },
        )
    if not can_manage_role(auth.user.role, target.role):
        raise _forbidden()

    changes = {}
    if body.role is not None:
        new_role = _parse_role(body.role)
        if not can_assign_role(auth.user.role, new_role):
            raise _forbidden()
        target.role = new_role.value
        changes["role"] = new_role.value
    if body.is_active is not None:
        target.is_active = body.is_active
        changes["is_active"] = body.is_active
        if not body.is_active:
            _revoke_sessions(db, target.id)
    db.commit()

    audit.record(
        db,
        "users.updated",
        user=auth.user,
        ip=client_ip(request),
        target=target.username,
        details=changes,
    )
    return serialize_user(target)


@router.post("/{user_id}/password")
def reset_password(
    user_id: int,
    body: ResetPasswordBody,
    request: Request,
    auth: AuthContext = Depends(manage_users),
    db: Session = Depends(get_db),
):
    target = _get_user(db, user_id)
    if target.id == auth.user.id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "cannot_modify_self",
                "message": "Use the change-password endpoint for your own account",
            },
        )
    if not can_manage_role(auth.user.role, target.role):
        raise _forbidden()

    validate_password(body.new_password, target.username)
    target.password_hash = hash_password(body.new_password)
    _revoke_sessions(db, target.id)
    db.commit()
    audit.record(
        db,
        "users.password_reset",
        user=auth.user,
        ip=client_ip(request),
        target=target.username,
    )
    return {"status": "ok"}