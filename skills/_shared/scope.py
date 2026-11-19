#!/usr/bin/env python3
"""
scope.py — deterministic engagement scope for cp-operation-pentest --infra.

An allowlist with **deny-wins** and **default-deny**: a URL is in scope only if its host
matches an `in_scope` entry and no `out_of_scope` entry. Keeps an audit of our own running
infra inside the boundary we declared — nothing is touched unless it is explicitly allowed.

Entry forms:
  - exact host            api.example.com
  - wildcard subdomain    *.staging.example.com   (one or more labels; not the apex)
  - CIDR                   10.0.0.0/8  /  2001:db8::/32

Pure standard library. Adapted from Claude-BugHunter's engine/scope.py (CC-BY-4.0).
"""
import ipaddress
from dataclasses import dataclass, field
from urllib.parse import urlparse


def host_of(url: str) -> str:
    """The host of a URL (or a bare host), lowercased, no port."""
    u = (url or "").strip()
    if "//" not in u:
        u = "//" + u
    netloc = urlparse(u).netloc or ""
    host = netloc.rsplit("@", 1)[-1]
    if host.startswith("["):                       # [ipv6]:port
        return host[1:].split("]", 1)[0].lower()
    return host.split(":", 1)[0].lower()


def _as_network(pattern: str):
    try:
        return ipaddress.ip_network(pattern, strict=False)
    except ValueError:
        return None


def _match(pattern: str, host: str) -> bool:
    pattern = (pattern or "").strip().lower()
    if not pattern:
        return False
    net = _as_network(pattern)
    if net is not None:
        try:
            return ipaddress.ip_address(host) in net
        except ValueError:
            return False
    if pattern.startswith("*."):
        suffix = pattern[1:]                        # ".staging.example.com"
        return host.endswith(suffix) and host != suffix[1:]
    return host == pattern


@dataclass
class Scope:
    name: str = ""
    in_scope: list = field(default_factory=list)
    out_of_scope: list = field(default_factory=list)
    seeds: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Scope":
        return cls(name=data.get("name", ""),
                   in_scope=list(data.get("in_scope") or []),
                   out_of_scope=list(data.get("out_of_scope") or []),
                   seeds=list(data.get("seeds") or []))

    def allows(self, url: str) -> bool:
        host = host_of(url)
        if not host:
            return False
        if any(_match(p, host) for p in self.out_of_scope):   # deny wins
            return False
        return any(_match(p, host) for p in self.in_scope)    # default deny

    def filter(self, urls) -> list:
        return [u for u in urls if self.allows(u)]
