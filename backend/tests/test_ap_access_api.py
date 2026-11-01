from fastapi.testclient import TestClient

from app.api import actions as actions_module
from app.devices.customer_router import CustomerRouterConnector
from app.main import app
from tests.test_ap_access import FakeApi

PASSWORD = "correct-horse-1"


def bootstrap(client):
    assert client.post(
        "/api/setup", json={"username": "boss", "password": PASSWORD, "password_confirm": PASSWORD}
    ).status_code == 201


def login(client, username="boss"):
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


class FakeConn:
    def __init__(self, ip, tid, api):
        self.ip = ip
        self.tid = tid
        self.api = api
        self.used = type("U", (), {"account_index": 0, "port": 2299})()
        self.failures = []

    def connect(self):
        return self

    def close(self):
        pass


def patch_connector(monkeypatch, api):
    def fake_make_connector(ip, tid):
        return FakeConn(ip, tid, api)

    monkeypatch.setattr(actions_module, "make_connector", fake_make_connector)


def test_nat_enter_requires_router_manage(client, monkeypatch):
    bootstrap(client)
    boss = login(client)
    assert client.post(
        "/api/users", json={"username": "viewer", "password": PASSWORD, "role": "read_only"}, headers=boss
    ).status_code == 201

    viewer = TestClient(app)
    headers = login(viewer, "viewer")
    body = {"ip": "10.229.1.1", "tid": "1001"}
    assert viewer.post("/api/router/manage/nat-enter", json=body, headers=headers).status_code == 403


def test_nat_enter_adds_the_rule_and_returns_the_pppoe_ip(client, monkeypatch):
    bootstrap(client)
    boss = login(client)
    api = FakeApi(ping_replies={"192.168.0.1": True})
    patch_connector(monkeypatch, api)

    response = client.post(
        "/api/router/manage/nat-enter", json={"ip": "10.229.1.1", "tid": "1001"}, headers=boss
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data == {"pppoe_ip": "10.229.1.1", "ap_ip": "192.168.0.1", "port": 90, "rule_added": True, "rule_state": "added"}


def test_nat_enter_fails_cleanly_when_no_ap_answers(client, monkeypatch):
    bootstrap(client)
    boss = login(client)
    patch_connector(monkeypatch, FakeApi())
    response = client.post(
        "/api/router/manage/nat-enter", json={"ip": "10.229.1.1", "tid": "1001"}, headers=boss
    )
    assert response.status_code == 422


def test_vpn_enter_sets_up_pptp_and_returns_both_ips(client, monkeypatch):
    bootstrap(client)
    boss = login(client)
    api = FakeApi(ping_replies={"10.10.10.2": True})
    patch_connector(monkeypatch, api)

    response = client.post(
        "/api/router/manage/vpn-enter", json={"ip": "10.229.1.2", "tid": "1002"}, headers=boss
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"pppoe_ip": "10.229.1.2", "ap_ip": "10.10.10.2"}
    assert len(api.secrets.rows) == 1