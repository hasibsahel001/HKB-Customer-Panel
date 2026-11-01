from fastapi.testclient import TestClient

from app.api import customer
from app.core.config import settings
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


def make_snapshot(username):
    def fake(ip, tid):
        ok = {"ok": True, "error": None, "error_type": None, "error_detail": None, "fetched_at": "t"}
        return {
            "ip": ip,
            "technical_id": tid,
            "connected_with_account": 0,
            "api_port": 2299,
            "fetched_at": "t",
            "sections": {
                "identity": {**ok, "data": {"identity": "Router-One"}},
                "pppoe": {
                    **ok,
                    "data": {
                        "username": username,
                        "running": True,
                        "status": "connected",
                        "matches_panel_ip": True,
                        "uptime": "10m",
                    },
                },
            },
        }

    return fake


def check(client, headers, ip, tid):
    response = client.post("/api/customer/check", json={"ip": ip, "tid": tid}, headers=headers)
    assert response.status_code == 200, response.text


def test_recent_list_dedupes_searches_and_orders(client, monkeypatch):
    bootstrap(client)
    headers = login(client)

    monkeypatch.setattr(customer, "collect_snapshot", make_snapshot("alpha"))
    check(client, headers, "10.229.1.1", "1001")
    check(client, headers, "10.229.1.1", "1001")
    monkeypatch.setattr(customer, "collect_snapshot", make_snapshot("bravo"))
    check(client, headers, "10.229.1.2", "1002")

    items = client.get("/api/customer/recent").json()["items"]
    assert [i["username"] for i in items] == ["bravo", "alpha"]
    assert items[0]["ip"] == "10.229.1.2"
    assert items[0]["identity"] == "Router-One"

    assert [i["username"] for i in client.get("/api/customer/recent", params={"q": "ALP"}).json()["items"]] == ["alpha"]
    assert [i["username"] for i in client.get("/api/customer/recent", params={"q": "1002"}).json()["items"]] == ["bravo"]
    assert client.get("/api/customer/recent", params={"q": "zzz"}).json()["items"] == []


def test_recent_list_is_private_per_user(client, monkeypatch):
    bootstrap(client)
    boss = login(client)
    monkeypatch.setattr(customer, "collect_snapshot", make_snapshot("alpha"))
    check(client, boss, "10.229.1.1", "1001")

    created = client.post(
        "/api/users",
        json={"username": "agent", "password": PASSWORD, "role": "support_agent"},
        headers=boss,
    )
    assert created.status_code == 201

    other = TestClient(app)
    login(other, "agent")
    assert other.get("/api/customer/recent").json()["items"] == []


def test_recent_list_respects_the_time_window(client, monkeypatch):
    bootstrap(client)
    headers = login(client)
    monkeypatch.setattr(customer, "collect_snapshot", make_snapshot("alpha"))
    check(client, headers, "10.229.1.1", "1001")
    assert len(client.get("/api/customer/recent").json()["items"]) == 1

    monkeypatch.setattr(settings, "recent_hours", 0)
    assert client.get("/api/customer/recent").json()["items"] == []


def test_recent_requires_login(client):
    assert client.get("/api/customer/recent").status_code == 401


def test_live_requires_login_and_validates_input(client, monkeypatch):
    assert client.post("/api/customer/live", json={"ip": "10.229.1.1", "tid": "1"}).status_code == 401
    bootstrap(client)
    headers = login(client)
    bad = client.post("/api/customer/live", json={"ip": "8.8.8.8", "tid": "1001"}, headers=headers)
    assert bad.status_code == 422