"""`_shared/scope.py` — deterministic engagement scope (allowlist, deny-wins, default-deny)."""
import pytest

from _shared import scope


def _scope():
    return scope.Scope.from_dict({
        "name": "ours",
        "in_scope": ["api.example.com", "*.staging.example.com", "10.0.0.0/8"],
        "out_of_scope": ["secret.staging.example.com"],
    })


def test_exact_host_in_scope():
    s = _scope()
    assert s.allows("https://api.example.com/users")
    assert not s.allows("https://api.evil.com/")


def test_wildcard_subdomain():
    s = _scope()
    assert s.allows("https://web.staging.example.com/")
    assert s.allows("http://a.b.staging.example.com/")
    # the apex of a wildcard is not itself in scope unless listed
    assert not s.allows("https://staging.example.com/")


def test_deny_wins_over_allow():
    s = _scope()
    # matches *.staging.example.com but is explicitly out of scope
    assert not s.allows("https://secret.staging.example.com/")


def test_cidr_in_scope():
    s = _scope()
    assert s.allows("http://10.1.2.3:8080/health")
    assert not s.allows("http://192.168.1.1/")


def test_default_deny_when_nothing_matches():
    s = scope.Scope.from_dict({"name": "x", "in_scope": [], "out_of_scope": []})
    assert not s.allows("https://anything.com/")


def test_hosts_in_scope_filters_a_list():
    s = _scope()
    urls = ["https://api.example.com/a", "https://evil.com/b",
            "https://web.staging.example.com/c", "https://secret.staging.example.com/d"]
    assert s.filter(urls) == ["https://api.example.com/a", "https://web.staging.example.com/c"]
