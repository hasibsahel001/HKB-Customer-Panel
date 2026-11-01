from fastapi.testclient import TestClient

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


def test_update_endpoints_require_login(client):
    body = {"ip": "10.229.1.1", "tid": "1001"}
    assert client.post("/api/router/update/check", json=body).status_code == 401
    assert client.post("/api/router/update/start", json={**body, "mode": "now"}).status_code == 401
    assert client.get("/api/router/update/jobs/abc").status_code == 401
    assert client.post("/api/router/firmware/upgrade", json=body).status_code == 401
    assert client.post("/api/router/usage-sample", json=body).status_code == 401


def test_only_admins_may_update_routers(client):
    bootstrap(client)
    boss = login(client)
    create(client, boss, "agent", "support_agent")
    create(client, boss, "viewer", "read_only")
    body = {"ip": "10.229.1.1", "tid": "1001"}

    for username in ("agent", "viewer"):
        other = TestClient(app)
        headers = login(other, username)
        assert other.post("/api/router/update/check", json=body, headers=headers).status_code == 403
        assert other.post("/api/router/update/start", json={**body, "mode": "now"}, headers=headers).status_code == 403
        assert other.post("/api/router/firmware/upgrade", json=body, headers=headers).status_code == 403


def test_input_is_validated_before_anything_starts(client):
    bootstrap(client)
    boss = login(client)
    outside = {"ip": "8.8.8.8", "tid": "1001"}
    assert client.post("/api/router/update/start", json={**outside, "mode": "now"}, headers=boss).status_code == 422
    assert client.post("/api/router/update/start", json={"ip": "10.229.1.1", "tid": "abc", "mode": "now"}, headers=boss).status_code == 422
    assert client.post("/api/router/update/start", json={"ip": "10.229.1.1", "tid": "1001", "mode": "sometime"}, headers=boss).status_code == 422
    assert client.post("/api/router/update/check", json=outside, headers=boss).status_code == 422


def test_unknown_job_is_not_found(client):
    bootstrap(client)
    boss = login(client)
    assert client.get("/api/router/update/jobs/does-not-exist").status_code == 404


def test_the_status_image_sampling_is_open_to_read_only_users(client):
    bootstrap(client)
    boss = login(client)
    create(client, boss, "viewer", "read_only")
    other = TestClient(app)
    headers = login(other, "viewer")
    outside = {"ip": "8.8.8.8", "tid": "1001"}
    # Allowed for the role, rejected only because the address is outside the allowed ranges.
    assert other.post("/api/router/usage-sample", json=outside, headers=headers).status_code == 422