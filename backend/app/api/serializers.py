from app.auth.permissions import permissions_for


def serialize_user(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "theme": user.theme,
        "created_at": user.created_at.isoformat(),
    }


def serialize_me(user, csrf_token: str) -> dict:
    data = serialize_user(user)
    data["permissions"] = sorted(p.value for p in permissions_for(user.role))
    data["csrf_token"] = csrf_token
    return data