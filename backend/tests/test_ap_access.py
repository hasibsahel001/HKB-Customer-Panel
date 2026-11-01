import pytest
from librouteros import exceptions as ros_exc

from app.services import router_actions as ra


class FakePingPath:
    """Supports the queries ensure_nat_rule and ensure_pptp_access make through api.path(...)."""

    def __init__(self, rows=None, fail_add_times=0):
        self.rows = rows or []
        self.fail_add_times = fail_add_times  # simulate the router rejecting add() with "already exists"
        self.add_calls = 0

    def __iter__(self):
        return iter(list(self.rows))

    def add(self, **kw):
        self.add_calls += 1
        if self.fail_add_times > 0:
            self.fail_add_times -= 1
            raise ros_exc.TrapError("failure: secret with the same name already exists")
        self.rows.append({".id": f"*{len(self.rows) + 1}", **kw})
        return self.rows[-1][".id"]

    def remove(self, *ids):
        self.rows[:] = [r for r in self.rows if r[".id"] not in ids]

    def update(self, **kw):
        row_id = kw.pop(".id")
        for row in self.rows:
            if row[".id"] == row_id:
                row.update(kw)
                return


class FakeApi:
    def __init__(self, ping_replies=None, nat_rows=None, secret_rows=None, fail_add_times=0):
        self.ping_replies = ping_replies or {}
        self.nat = FakePingPath(nat_rows)
        self.secrets = FakePingPath(secret_rows, fail_add_times=fail_add_times)
        self.commands = []

    def path(self, *parts):
        if parts == ("ip", "firewall", "nat"):
            return self.nat
        if parts == ("ppp", "secret"):
            return self.secrets
        raise KeyError(parts)

    def rawCmd(self, cmd, *words):
        self.commands.append((cmd, words))
        if cmd == "/ip/firewall/nat/move":
            moved = next(w.split("=", 2)[2] for w in words if w.startswith("=numbers="))
            target = next(w.split("=", 2)[2] for w in words if w.startswith("=destination="))
            rows = self.nat.rows
            row = next(r for r in rows if r[".id"] == moved)
            rows.remove(row)
            rows.insert(next(i for i, r in enumerate(rows) if r[".id"] == target), row)
            return iter([])
        if cmd == "/ping":
            address = next(w.split("=", 2)[2] for w in words if w.startswith("=address="))
            received = "1" if self.ping_replies.get(address) else "0"
            return iter([{"received": received}])
        return iter([])


def matching_secret(id_=".id1"):
    return {
        ".id": id_,
        "name": "1",
        "password": "1",
        "profile": "*0",
        "local-address": "1.1.1.23",
        "remote-address": "1.1.1.25",
        "service": "any",
    }


def test_find_customer_ap_ip_returns_the_first_that_answers():
    api = FakeApi(ping_replies={"192.168.0.1": True})
    assert ra.find_customer_ap_ip(api, ["10.10.10.2", "192.168.0.1", "192.168.1.1"]) == "192.168.0.1"


def test_find_customer_ap_ip_tries_in_priority_order():
    api = FakeApi(ping_replies={"10.10.10.2": True, "192.168.0.1": True})
    assert ra.find_customer_ap_ip(api, ["10.10.10.2", "192.168.0.1", "192.168.1.1"]) == "10.10.10.2"


def test_find_customer_ap_ip_none_answer():
    api = FakeApi()
    assert ra.find_customer_ap_ip(api, ["10.10.10.2", "192.168.0.1"]) is None


def nat_row(id_, to_address, **extra):
    row = {
        ".id": id_,
        "chain": "dstnat",
        "protocol": "tcp",
        "dst-port": "90",
        "action": "dst-nat",
        "to-addresses": to_address,
        "to-ports": "80",
    }
    row.update(extra)
    return row


def test_ensure_nat_rule_adds_once_and_is_idempotent():
    api = FakeApi()
    assert ra.ensure_nat_rule(api, "10.10.10.2") == "added"
    assert len(api.nat.rows) == 1
    row = api.nat.rows[0]
    assert row["chain"] == "dstnat"
    assert row["protocol"] == "tcp"
    assert row["dst-port"] == "90"
    assert row["action"] == "dst-nat"
    assert row["to-addresses"] == "10.10.10.2"
    assert row["to-ports"] == "80"

    assert ra.ensure_nat_rule(api, "10.10.10.2") == "unchanged"
    assert len(api.nat.rows) == 1


def test_ensure_nat_rule_edits_an_old_port_90_rule_instead_of_adding_a_shadowed_one():
    api = FakeApi(nat_rows=[nat_row("*1", "192.168.0.1")])
    assert ra.ensure_nat_rule(api, "10.10.10.2") == "updated"
    assert len(api.nat.rows) == 1
    assert api.nat.rows[0]["to-addresses"] == "10.10.10.2"


def test_ensure_nat_rule_moves_the_rule_to_the_top():
    other = {".id": "*1", "chain": "srcnat", "action": "masquerade"}
    api = FakeApi(nat_rows=[other, nat_row("*2", "10.10.10.2")])
    assert ra.ensure_nat_rule(api, "10.10.10.2") == "moved"
    assert [r[".id"] for r in api.nat.rows] == ["*2", "*1"]


def test_ensure_nat_rule_adds_a_new_rule_at_the_top_when_there_was_none():
    api = FakeApi(nat_rows=[{".id": "*1", "chain": "srcnat", "action": "masquerade"}])
    assert ra.ensure_nat_rule(api, "10.10.10.2") == "added"
    assert api.nat.rows[0]["to-addresses"] == "10.10.10.2"
    assert len(api.nat.rows) == 2


def test_ensure_nat_rule_enables_a_disabled_rule():
    api = FakeApi(nat_rows=[nat_row("*1", "10.10.10.2", disabled=True)])
    assert ra.ensure_nat_rule(api, "10.10.10.2") == "updated"
    assert api.nat.rows[0]["disabled"] == "no"


def test_ensure_pptp_access_creates_the_secret_when_missing():
    api = FakeApi()
    assert ra.ensure_pptp_access(api) is True
    assert ("/interface/pptp-server/server/set", ("=enabled=yes", "=authentication=pap,chap,mschap1,mschap2")) in api.commands
    assert len(api.secrets.rows) == 1
    row = api.secrets.rows[0]
    assert row["name"] == "1"
    assert row["password"] == "1"
    assert row["profile"] == "*0"
    assert row["local-address"] == "1.1.1.23"
    assert row["remote-address"] == "1.1.1.25"
    assert row["service"] == "any"


def test_ensure_pptp_access_leaves_a_matching_secret_untouched_and_never_calls_add():
    api = FakeApi(secret_rows=[matching_secret()])
    before = list(api.secrets.rows)
    assert ra.ensure_pptp_access(api) is False
    assert api.secrets.rows == before
    assert api.secrets.add_calls == 0


def test_ensure_pptp_access_fixes_a_mismatched_secret_in_place_without_add():
    wrong = matching_secret()
    wrong["password"] = "old-password"
    api = FakeApi(secret_rows=[wrong])
    assert ra.ensure_pptp_access(api) is True
    assert api.secrets.add_calls == 0
    assert len(api.secrets.rows) == 1
    assert api.secrets.rows[0]["password"] == "1"
    assert api.secrets.rows[0][".id"] == wrong[".id"]


def test_ensure_pptp_access_deduplicates_if_more_than_one_secret_named_1_exists():
    api = FakeApi(secret_rows=[matching_secret(".id1"), matching_secret(".id2")])
    assert ra.ensure_pptp_access(api) is True
    assert len(api.secrets.rows) == 1
    assert api.secrets.rows[0][".id"] == ".id1"


def test_ensure_pptp_access_never_raises_a_duplicate_name_error_on_repeated_calls():
    """Regression test for the 'secret with the same name already exists' failure on a real router."""
    api = FakeApi(secret_rows=[matching_secret()])
    for _ in range(3):
        ra.ensure_pptp_access(api)
    assert len(api.secrets.rows) == 1


def test_ensure_pptp_access_recovers_when_the_router_rejects_add_as_a_duplicate():
    """Our own read found nothing named '1', but the router's add() still says it already exists
    (a stale read or a race). The fallback removes whatever is really there and recreates once."""
    api = FakeApi(secret_rows=[], fail_add_times=1)
    # Make the router's own add() reject once, as if a secret existed that our read missed:
    # simulate that by having the fallback's remove+retry succeed on the second add() call.
    assert ra.ensure_pptp_access(api) is True
    assert len(api.secrets.rows) == 1
    assert api.secrets.rows[0]["name"] == "1"
    assert api.secrets.add_calls == 2  # the failed attempt, then the successful retry


def test_ensure_pptp_access_raises_the_real_error_if_the_retry_also_fails():
    api = FakeApi(secret_rows=[], fail_add_times=2)  # every add() attempt fails
    with pytest.raises(ra.RouterCommandFailed):
        ra.ensure_pptp_access(api)


def test_ensure_pptp_access_other_trap_errors_are_not_treated_as_duplicates():
    class FailingPath(FakePingPath):
        def add(self, **kw):
            raise ros_exc.TrapError("failure: no such profile")

    api = FakeApi()
    api.secrets = FailingPath()
    with pytest.raises(ra.RouterCommandFailed, match="no such profile"):
        ra.ensure_pptp_access(api)