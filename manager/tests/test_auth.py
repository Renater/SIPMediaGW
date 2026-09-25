"""auth: password hashing and rule, login throttle."""
from unittest.mock import Mock

import auth


def request(ip="10.0.0.1"):
    return Mock(client=Mock(host=ip))


def test_password_hash_round_trip():
    stored = auth.hashPassword("a long enough passphrase")
    assert stored.startswith("scrypt$") and "a long enough" not in stored
    assert auth.checkPassword("a long enough passphrase", stored) is True
    assert auth.checkPassword("A long enough passphrase", stored) is False
    assert auth.checkPassword("", stored) is False
    # Two hashes of one password differ: the salt is per account.
    assert auth.hashPassword("a long enough passphrase") != stored


def test_an_account_without_a_hash_refuses_everything():
    """A ProConnect account has no local password: nothing signs it in here."""
    assert auth.checkPassword("anything at all", None) is False
    assert auth.checkPassword("anything at all", "") is False
    assert auth.checkPassword("anything at all", "garbage") is False


def test_password_rule_is_length_first(monkeypatch):
    """ANSSI: length over composition. The other rules are the obvious ones."""
    monkeypatch.setattr(auth, "MIN_PASSWORD_LENGTH", 11)
    assert auth.passwordProblem("short1$", "alice")
    assert auth.passwordProblem("x" * 257, "alice")
    assert auth.passwordProblem("ALICEALICEALICE", "aliceAliceAlice")
    assert auth.passwordProblem(auth.DEFAULT_PASSWORD, "alice")
    assert auth.passwordProblem("same passphrase", "alice", current="same passphrase")
    assert auth.passwordProblem("correct horse battery", "alice") is None
    assert auth.passwordProblem("onlyletters", "alice") is None, "no composition rule"


def test_throttle_after_max_failures(monkeypatch):
    monkeypatch.setattr(auth, "_failures", {})
    r = request()
    for _ in range(auth.maxFailures):
        assert auth.loginThrottled(r) is False
        auth.recordLoginFailure(r)
    assert auth.loginThrottled(r) is True
    assert auth.loginThrottled(request("10.0.0.2")) is False   # per IP
    auth.clearLoginFailures(r)
    assert auth.loginThrottled(r) is False


class _Req:
    """Enough of a request for the throttle: an address and headers."""
    def __init__(self, host, forwarded=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {"X-Forwarded-For": forwarded} if forwarded else {}


def test_throttle_keys_on_forwarded_address_behind_a_proxy(monkeypatch):
    """
    Two clients behind one proxy share its address. Without the forwarded
    header, five failures by the first lock out the second — which is what
    happened to the console behind the TLS proxy the code recommends.
    """
    monkeypatch.setattr(auth, "trustProxy", True)
    monkeypatch.setattr(auth, "trustedProxies", auth.parseProxies("10.0.0.1"))   # the proxy, declared
    auth._failures.clear()
    attacker = _Req("10.0.0.1", forwarded="203.0.113.7")
    operator = _Req("10.0.0.1", forwarded="198.51.100.4")
    for _ in range(auth.maxFailures):
        auth.recordLoginFailure(attacker)
    assert auth.loginThrottled(attacker)
    assert not auth.loginThrottled(operator), "a neighbour behind the same proxy was locked out"


def test_forwarded_header_is_ignored_without_a_trusted_proxy(monkeypatch):
    """Read unconditionally, the header lets a direct client forge any address."""
    monkeypatch.setattr(auth, "trustProxy", False)
    auth._failures.clear()
    direct = _Req("10.0.0.1", forwarded="1.2.3.4")
    for _ in range(auth.maxFailures):
        auth.recordLoginFailure(direct)
    forged = _Req("10.0.0.1", forwarded="5.6.7.8")
    assert auth.loginThrottled(forged), "a forged header escaped the throttle"


def test_forged_first_entry_does_not_escape_the_throttle(monkeypatch):
    """
    The proxy appends the address it saw; the client controls what comes
    before. Five failures with five different forged prefixes are still five
    failures from the one real address.
    """
    monkeypatch.setattr(auth, "trustProxy", True)
    monkeypatch.setattr(auth, "trustedProxies", auth.parseProxies("10.0.0.1"))   # the proxy, declared
    auth._failures.clear()
    for n in range(auth.maxFailures):
        auth.recordLoginFailure(_Req("10.0.0.1", forwarded=f"1.2.3.{n}, 203.0.113.7"))
    assert auth.loginThrottled(_Req("10.0.0.1", forwarded="9.9.9.9, 203.0.113.7")), \
        "a forged first entry escaped the throttle"


def test_expired_failures_are_pruned(monkeypatch):
    """A spray of addresses must not grow the dict for the life of the process."""
    monkeypatch.setattr(auth, "trustProxy", False)
    auth._failures.clear()
    auth.recordLoginFailure(_Req("10.0.0.1"))
    auth._failures["10.0.0.1"][1] = 0                  # already expired
    auth.recordLoginFailure(_Req("10.0.0.2"))
    assert "10.0.0.1" not in auth._failures
    assert auth._failures["10.0.0.2"][0] == 1
