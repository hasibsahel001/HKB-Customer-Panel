from fastapi.testclient import TestClient

from app.api import customer
from app.main import app

PASSWORD = "correct-horse-1"


def bootstrap(client):
    response = client.post(
        "/api/setup",
        json={"username": "boss", "password": PASSWORD, "password_confirm": PASSWORD},
    )
    assert response.status_code == 201


def login(client, username="boss"):
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def create(client, headers, username, role):
    response = client.post(
        "/api/users", json={"username": username, "password": PASSWORD, "role": role}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def fake_snapshot(ip, tid):
    ok = {"ok": True, "error": None, "error_type": None, "error_detail": None, "fetched_at": "t"}
    return {
        "ip": ip,
        "technical_id": tid,
        "connected_with_account": 0,
        "api_port": 2299,
        "fetched_at": "t",
        "sections": {"pppoe": {**ok, "data": {"username": f"user-{tid}", "running": True, "status": "connected", "matches_panel_ip": True}}},
    }


def test_delete_user_rules(client):
    bootstrap(client)
    boss = login(client)
    admin_id = create(client, boss, "admin1", "admin")
    agent_id = create(client, boss, "agent", "support_agent")

    agent_client = TestClient(app)
    login(agent_client, "agent")
    assert agent_client.get("/api/auth/me").status_code == 200

    admin_client = TestClient(app)
    admin = login(admin_client, "admin1")
    assert admin_client.delete("/api/users/1", headers=admin).status_code == 403          # super admin
    assert admin_client.delete(f"/api/users/{admin_id}", headers=admin).status_code == 400  # self
    assert admin_client.delete("/api/users/999", headers=admin).status_code == 404
    assert admin_client.delete(f"/api/users/{agent_id}").status_code == 403               # no CSRF token
    assert admin_client.delete(f"/api/users/{agent_id}", headers=admin).status_code == 200

    assert agent_client.get("/api/auth/me").status_code == 401  # their sessions were removed
    retry = TestClient(app).post("/api/auth/login", json={"username": "agent", "password": PASSWORD})
    assert retry.status_code == 401
    usernames = [u["username"] for u in client.get("/api/users").json()]
    assert "agent" not in usernames

    actions = {i["action"]: i for i in client.get("/api/audit").json()["items"]}
    assert actions["users.deleted"]["target"] == "agent"


def test_agents_cannot_delete_anyone(client):
    bootstrap(client)
    boss = login(client)
    create(client, boss, "agent", "support_agent")
    viewer_id = create(client, boss, "viewer", "read_only")
    agent_client = TestClient(app)
    agent = login(agent_client, "agent")
    assert agent_client.delete(f"/api/users/{viewer_id}", headers=agent).status_code == 403


def test_clear_audit_is_super_admin_only_and_leaves_a_trace(client):
    bootstrap(client)
    boss = login(client)
    create(client, boss, "admin1", "admin")
    admin_client = TestClient(app)
    admin = login(admin_client, "admin1")
    assert admin_client.delete("/api/audit", headers=admin).status_code == 403

    before = client.get("/api/audit").json()["total"]
    assert before > 1
    assert client.delete("/api/audit?older_than_days=30", headers=boss).json() == {"deleted": 0}

    result = client.delete("/api/audit", headers=boss)
    assert result.status_code == 200
    assert result.json()["deleted"] >= before - 1

    remaining = client.get("/api/audit").json()
    assert remaining["total"] == 1
    assert remaining["items"][0]["action"] == "audit.cleared"


def test_recent_can_be_cleared_for_me_or_for_everyone(client, monkeypatch):
    monkeypatch.setattr(customer, "collect_snapshot", fake_snapshot)
    bootstrap(client)
    boss = login(client)
    create(client, boss, "admin1", "admin")
    create(client, boss, "agent", "support_agent")

    agent_client = TestClient(app)
    agent = login(agent_client, "agent")
    admin_client = TestClient(app)
    admin = login(admin_client, "admin1")

    for http, headers, tid in ((client, boss, "1001"), (agent_client, agent, "1002"), (admin_client, admin, "1003")):
        response = http.post("/api/customer/check", json={"ip": "10.229.1.1", "tid": tid}, headers=headers)
        assert response.status_code == 200, response.text

    assert agent_client.delete("/api/customer/recent/all", headers=agent).status_code == 403
    assert agent_client.delete("/api/customer/recent/mine", headers=agent).json() == {"deleted": 1}
    assert agent_client.get("/api/customer/recent").json()["items"] == []
    assert len(client.get("/api/customer/recent").json()["items"]) == 1  # others are untouched

    assert admin_client.delete("/api/customer/recent/all", headers=admin).json() == {"deleted": 2}
    assert client.get("/api/customer/recent").json()["items"] == []
    assert admin_client.delete("/api/customer/recent/mine").status_code == 403  # no CSRF token