from datetime import timedelta

from fastapi.testclient import TestClient

from app.api import customer
from app.auth import deps
from app.core.config import settings
from app.core.errors import ConnectionFailed, InvalidInput
from app.main import app
from app.models import utcnow

PASSWORD = "correct-horse-1"


def bootstrap(client, username="boss", password=PASSWORD):
    response = client.post(
        "/api/setup",
        json={"username": username, "password": password, "password_confirm": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client, username="boss", password=PASSWORD):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def create_user(client, headers, username, role, password=PASSWORD):
    return client.post(
        "/api/users",
        json={"username": username, "password": password, "role": role},
        headers=headers,
    )


def fake_snapshot(ip, tid):
    failed = {
        "ok": False,
        "data": None,
        "error": "unavailable",
        "error_type": "RuntimeError",
        "error_detail": "internal detail text",
        "fetched_at": "t",
    }
    return {
        "ip": ip,
        "technical_id": tid,
        "connected_with_account": 2,
        "api_port": 2299,
        "fetched_at": "t",
        "sections": {
            "temperature": dict(failed),
            "queues": {**failed, "error_detail": "something odd"},
        },
    }


def test_setup_flow(client):
    assert client.get("/api/setup/status").json() == {"needs_setup": True}

    mismatch = client.post(
        "/api/setup",
        json={"username": "boss", "password": PASSWORD, "password_confirm": "different-pass-1"},
    )
    assert mismatch.status_code == 422

    short = client.post(
        "/api/setup",
        json={"username": "boss", "password": "short", "password_confirm": "short"},
    )
    assert short.status_code == 422

    created = bootstrap(client)
    assert created["role"] == "super_admin"

    again = client.post(
        "/api/setup",
        json={"username": "other", "password": PASSWORD, "password_confirm": PASSWORD},
    )
    assert again.status_code == 409
    assert client.get("/api/setup/status").json() == {"needs_setup": False}


def test_login_me_logout_and_csrf(client):
    bootstrap(client)
    assert client.get("/api/auth/me").status_code == 401

    bad = client.post("/api/auth/login", json={"username": "boss", "password": "wrong-password-1"})
    assert bad.status_code == 401
    assert bad.json()["detail"]["code"] == "invalid_credentials"

    headers = login(client)
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "super_admin"
    assert "users.manage" in me.json()["permissions"]

    no_csrf = client.post("/api/auth/logout")
    assert no_csrf.status_code == 403
    assert no_csrf.json()["detail"]["code"] == "csrf_failed"

    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_lockout_after_repeated_failures(client):
    bootstrap(client)
    for _ in range(3):
        response = client.post("/api/auth/login", json={"username": "boss", "password": "wrong-password-1"})
        assert response.status_code == 401
    blocked = client.post("/api/auth/login", json={"username": "boss", "password": PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "too_many_attempts"


def test_session_idle_expiry(client, monkeypatch):
    bootstrap(client)
    login(client)
    assert client.get("/api/auth/me").status_code == 200

    real_now = utcnow()
    monkeypatch.setattr(deps, "utcnow", lambda: real_now + timedelta(hours=2))
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_expired"


def test_change_password_and_session_revocation(client):
    bootstrap(client)
    headers = login(client)

    other = TestClient(app)
    login(other)
    assert other.get("/api/auth/me").status_code == 200

    wrong = client.post(
        "/api/auth/change-password",
        json={"current_password": "wrong-password-1", "new_password": "brand-new-pass-1"},
        headers=headers,
    )
    assert wrong.status_code == 400

    ok = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "brand-new-pass-1"},
        headers=headers,
    )
    assert ok.status_code == 200

    assert client.get("/api/auth/me").status_code == 200  # current session survives
    assert other.get("/api/auth/me").status_code == 401   # other sessions are revoked

    fresh = TestClient(app)
    old_login = fresh.post("/api/auth/login", json={"username": "boss", "password": PASSWORD})
    assert old_login.status_code == 401
    new_login = fresh.post("/api/auth/login", json={"username": "boss", "password": "brand-new-pass-1"})
    assert new_login.status_code == 200


def test_theme_preference(client):
    bootstrap(client)
    headers = login(client)
    assert client.patch("/api/auth/me", json={"theme": "dark"}, headers=headers).json()["theme"] == "dark"
    assert client.patch("/api/auth/me", json={"theme": "neon"}, headers=headers).status_code == 422


def test_role_permissions_are_enforced_in_backend(client):
    bootstrap(client)
    boss = login(client)
    assert create_user(client, boss, "admin1", "admin").status_code == 201
    assert create_user(client, boss, "agent", "support_agent").status_code == 201
    assert create_user(client, boss, "viewer", "read_only").status_code == 201

    agent_client = TestClient(app)
    agent = login(agent_client, "agent")
    assert agent_client.get("/api/users").status_code == 403
    assert agent_client.get("/api/audit").status_code == 403
    assert create_user(agent_client, agent, "x-user", "read_only").status_code == 403

    viewer_client = TestClient(app)
    login(viewer_client, "viewer")
    assert viewer_client.get("/api/users").status_code == 403

    admin_client = TestClient(app)
    admin = login(admin_client, "admin1")
    assert admin_client.get("/api/users").status_code == 200
    assert admin_client.get("/api/audit").status_code == 403
    assert create_user(admin_client, admin, "agent2", "support_agent").status_code == 201
    assert create_user(admin_client, admin, "admin2", "admin").status_code == 403
    assert create_user(admin_client, admin, "boss2", "super_admin").status_code == 403

    # Admin cannot touch the Super Admin (user id 1).
    blocked = admin_client.patch("/api/users/1", json={"is_active": False}, headers=admin)
    assert blocked.status_code == 403


def test_user_management_rules(client):
    bootstrap(client)
    boss = login(client)

    created = create_user(client, boss, "agent", "support_agent")
    assert created.status_code == 201
    assert create_user(client, boss, "agent", "support_agent").status_code == 409
    assert create_user(client, boss, "weird", "wizard").status_code == 422
    assert create_user(client, boss, "weakling", "read_only", password="short").status_code == 422

    self_change = client.patch("/api/users/1", json={"is_active": False}, headers=boss)
    assert self_change.status_code == 400
    assert self_change.json()["detail"]["code"] == "cannot_modify_self"


def test_deactivating_a_user_revokes_sessions(client):
    bootstrap(client)
    boss = login(client)
    agent_id = create_user(client, boss, "agent", "support_agent").json()["id"]

    agent_client = TestClient(app)
    login(agent_client, "agent")
    assert agent_client.get("/api/auth/me").status_code == 200

    off = client.patch(f"/api/users/{agent_id}", json={"is_active": False}, headers=boss)
    assert off.status_code == 200
    assert agent_client.get("/api/auth/me").status_code == 401
    retry = TestClient(app).post("/api/auth/login", json={"username": "agent", "password": PASSWORD})
    assert retry.status_code == 401


def test_admin_password_reset_revokes_sessions(client):
    bootstrap(client)
    boss = login(client)
    agent_id = create_user(client, boss, "agent", "support_agent").json()["id"]

    agent_client = TestClient(app)
    login(agent_client, "agent")

    reset = client.post(
        f"/api/users/{agent_id}/password", json={"new_password": "reset-pass-12345"}, headers=boss
    )
    assert reset.status_code == 200
    assert agent_client.get("/api/auth/me").status_code == 401
    assert TestClient(app).post(
        "/api/auth/login", json={"username": "agent", "password": "reset-pass-12345"}
    ).status_code == 200


def test_sessions_list_and_revoke(client):
    bootstrap(client)
    headers = login(client)
    second = TestClient(app)
    login(second)

    sessions = client.get("/api/auth/sessions").json()
    assert len(sessions) == 2
    assert sum(1 for s in sessions if s["current"]) == 1

    other_id = next(s["id"] for s in sessions if not s["current"])
    assert client.delete(f"/api/auth/sessions/{other_id}", headers=headers).status_code == 200
    assert second.get("/api/auth/me").status_code == 401
    assert client.delete("/api/auth/sessions/99999", headers=headers).status_code == 404


def test_customer_check_requires_login(client):
    response = client.post("/api/customer/check", json={"ip": "10.229.1.1", "tid": "1234"})
    assert response.status_code == 401


def test_customer_check_hides_debug_details_from_agents(client, monkeypatch):
    monkeypatch.setattr(customer, "collect_snapshot", fake_snapshot)
    bootstrap(client)
    boss = login(client)
    create_user(client, boss, "agent", "support_agent")
    create_user(client, boss, "admin1", "admin")
    payload = {"ip": "10.229.1.1", "tid": "1234"}

    agent_client = TestClient(app)
    agent = login(agent_client, "agent")
    agent_response = agent_client.post("/api/customer/check", json=payload, headers=agent)
    assert agent_response.status_code == 200
    assert "error_detail" not in agent_response.text
    assert "something odd" not in agent_response.text
    assert agent_response.json()["diagnostics"]["findings"]

    admin_client = TestClient(app)
    admin = login(admin_client, "admin1")
    admin_response = admin_client.post("/api/customer/check", json=payload, headers=admin)
    assert admin_response.status_code == 200
    assert "something odd" in admin_response.text

    audit = client.get("/api/audit", params={"action": "customer.check"}).json()
    assert audit["total"] == 2
    assert all(item["success"] for item in audit["items"])


def test_customer_check_error_mapping(client, monkeypatch):
    bootstrap(client)
    boss = login(client)
    payload = {"ip": "10.229.1.1", "tid": "1234"}

    def raise_invalid(ip, tid):
        raise InvalidInput("The address is outside the allowed management ranges")

    monkeypatch.setattr(customer, "collect_snapshot", raise_invalid)
    invalid = client.post("/api/customer/check", json=payload, headers=boss)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_input"

    def raise_unreachable(ip, tid):
        raise ConnectionFailed([])

    monkeypatch.setattr(customer, "collect_snapshot", raise_unreachable)
    unreachable = client.post("/api/customer/check", json=payload, headers=boss)
    assert unreachable.status_code == 502
    assert unreachable.json()["detail"]["code"] == "router_unreachable"


def test_customer_check_rate_limit(client, monkeypatch):
    monkeypatch.setattr(customer, "collect_snapshot", fake_snapshot)
    monkeypatch.setattr(settings, "customer_checks_per_minute", 2)
    bootstrap(client)
    boss = login(client)
    payload = {"ip": "10.229.1.1", "tid": "1234"}

    assert client.post("/api/customer/check", json=payload, headers=boss).status_code == 200
    assert client.post("/api/customer/check", json=payload, headers=boss).status_code == 200
    limited = client.post("/api/customer/check", json=payload, headers=boss)
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "rate_limited"


def test_audit_never_contains_passwords(client):
    bootstrap(client)
    attacker_password = "super-secret-wrong-pw"
    client.post("/api/auth/login", json={"username": "boss", "password": attacker_password})
    login(client)

    response = client.get("/api/audit")
    assert response.status_code == 200
    assert attacker_password not in response.text
    assert PASSWORD not in response.text
    actions = {item["action"] for item in response.json()["items"]}
    assert {"setup.super_admin_created", "auth.login_failed", "auth.login"} <= actions