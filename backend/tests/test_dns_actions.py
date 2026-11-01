import pytest
from fastapi.testclient import TestClient

from app.api import actions as actions_module
from app.core.errors import InvalidInput
from app.main import app
from app.services import router_actions as ra

PASSWORD = "correct-horse-1"


class FakeDnsPath:
    def __init__(self, row):
        self.row = row
        self.updated = None

    def __iter__(self):
        return iter([self.row] if self.row else [])

    def update(self, **kw):
        self.updated = kw
        self.row.update(kw)


class FakeApi:
    def __init__(self, row):
        self.dns = FakeDnsPath(row)

    def path(self, *parts):
        assert parts == ("ip", "dns")
        return self.dns


def test_read_dns_splits_manual_and_dynamic_servers():
    api = FakeApi({"servers": "8.8.8.8,1.1.1.1", "dynamic-servers": "10.229.0.1", "allow-remote-requests": "true"})
    info = ra.read_dns(api)
    assert info == {
        "servers": ["8.8.8.8", "1.1.1.1"],
        "dynamic_servers": ["10.229.0.1"],
        "allow_remote_requests": True,
    }


def test_read_dns_with_nothing_set():
    info = ra.read_dns(FakeApi({}))
    assert info == {"servers": [], "dynamic_servers": [], "allow_remote_requests": False}


def test_save_dns_validates_each_address():
    api = FakeApi({"servers": "", "dynamic-servers": "", "allow-remote-requests": "false"})
    with pytest.raises(InvalidInput):
        ra.save_dns(api, ["not-an-ip"], True)


def test_save_dns_rejects_more_than_four_servers():
    api = FakeApi({"servers": "", "dynamic-servers": "", "allow-remote-requests": "false"})
    with pytest.raises(InvalidInput):
        ra.save_dns(api, ["1.1.1.1", "2.2.2.2", "3.3.3.3", "4.4.4.4", "5.5.5.5"], True)


def test_save_dns_updates_servers_and_the_remote_requests_flag():
    api = FakeApi({"servers": "", "dynamic-servers": "10.229.0.1", "allow-remote-requests": "false"})
    result = ra.save_dns(api, ["8.8.8.8", "1.1.1.1"], True)
    assert api.dns.updated["servers"] == "8.8.8.8,1.1.1.1"
    assert api.dns.updated["allow-remote-requests"] == "yes"
    assert result["servers"] == ["8.8.8.8", "1.1.1.1"]
    assert result["allow_remote_requests"] is True


def test_save_dns_ignores_blank_entries():
    api = FakeApi({"servers": "", "dynamic-servers": "", "allow-remote-requests": "false"})
    ra.save_dns(api, ["8.8.8.8", "", "  "], False)
    assert api.dns.updated["servers"] == "8.8.8.8"


def bootstrap(client):
    assert client.post(
        "/api/setup", json={"username": "boss", "password": PASSWORD, "password_confirm": PASSWORD}
    ).status_code == 201


def login(client):
    response = client.post("/api/auth/login", json={"username": "boss", "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


class FakeConn:
    def __init__(self, ip, tid, api):
        self.ip = ip
        self.tid = tid
        self.api = api

    def connect(self):
        return self

    def close(self):
        pass


def test_dns_get_and_save_via_api(client, monkeypatch):
    bootstrap(client)
    headers = login(client)
    api = FakeApi({"servers": "8.8.8.8", "dynamic-servers": "10.229.0.1", "allow-remote-requests": "false"})
    monkeypatch.setattr(actions_module, "make_connector", lambda ip, tid: FakeConn(ip, tid, api))

    got = client.post("/api/router/dns/get", json={"ip": "10.229.1.1", "tid": "1001"}, headers=headers)
    assert got.status_code == 200, got.text
    assert got.json()["servers"] == ["8.8.8.8"]

    saved = client.post(
        "/api/router/dns/save",
        json={"ip": "10.229.1.1", "tid": "1001", "servers": ["1.1.1.1"], "allow_remote_requests": True},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["servers"] == ["1.1.1.1"]