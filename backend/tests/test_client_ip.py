from types import SimpleNamespace

from app.auth.deps import client_ip


def make(host, forwarded=None):
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers)


def test_forwarded_address_is_used_only_behind_the_local_proxy():
    assert client_ip(make("127.0.0.1", "192.168.255.30")) == "192.168.255.30"
    assert client_ip(make("192.168.255.40", "10.0.0.1")) == "192.168.255.40"


def test_last_entry_wins_so_a_forged_first_entry_is_ignored():
    assert client_ip(make("127.0.0.1", "1.2.3.4, 192.168.255.30")) == "192.168.255.30"


def test_invalid_forwarded_value_is_ignored():
    assert client_ip(make("127.0.0.1", "not-an-ip")) == "127.0.0.1"


def test_missing_client():
    assert client_ip(SimpleNamespace(client=None, headers={})) is None