from enum import Enum


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    SUPPORT_AGENT = "support_agent"
    READ_ONLY = "read_only"


class Permission(str, Enum):
    CUSTOMER_CHECK = "customer.check"
    ROUTER_MANAGE = "router.manage"   # edit queues, reboot customer routers
    ROUTER_UPDATE = "router.update"   # update RouterOS and the Routerboard firmware
    DEBUG_VIEW = "debug.view"
    USERS_MANAGE = "users.manage"
    AUDIT_VIEW = "audit.view"
    AUDIT_DELETE = "audit.delete"
    SETTINGS_MANAGE = "settings.manage"


ROLE_PERMISSIONS = {
    Role.SUPER_ADMIN: set(Permission),
    Role.ADMIN: {
        Permission.CUSTOMER_CHECK,
        Permission.ROUTER_MANAGE,
        Permission.ROUTER_UPDATE,
        Permission.DEBUG_VIEW,
        Permission.USERS_MANAGE,
    },
    Role.SUPPORT_AGENT: {Permission.CUSTOMER_CHECK, Permission.ROUTER_MANAGE},
    Role.READ_ONLY: {Permission.CUSTOMER_CHECK},
}

# Roles an Admin is allowed to create, edit, reset and delete.
_ADMIN_MANAGEABLE = {Role.SUPPORT_AGENT, Role.READ_ONLY}


def to_role(value):
    try:
        return Role(value)
    except ValueError:
        return None


def permissions_for(role) -> set:
    parsed = to_role(role)
    if parsed is None:
        return set()
    return set(ROLE_PERMISSIONS.get(parsed, set()))


def has_permission(role, permission: Permission) -> bool:
    return permission in permissions_for(role)


def can_manage_role(actor_role, target_role) -> bool:
    """Whether the actor may edit users that currently hold target_role."""
    actor = to_role(actor_role)
    target = to_role(target_role)
    if actor is None or target is None:
        return False
    if actor == Role.SUPER_ADMIN:
        return True
    if actor == Role.ADMIN:
        return target in _ADMIN_MANAGEABLE
    return False


def can_assign_role(actor_role, new_role) -> bool:
    """Whether the actor may give new_role to a user."""
    return can_manage_role(actor_role, new_role)