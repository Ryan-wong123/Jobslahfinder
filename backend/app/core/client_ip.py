from __future__ import annotations

import ipaddress
import os

from fastapi import Request


TRUSTED_PROXY_CIDRS_ENV = "TRUSTED_PROXY_CIDRS"
RISK_ENGINE_TRUSTED_PROXY_CIDRS_ENV = "RISK_ENGINE_TRUSTED_PROXY_CIDRS"
DEFAULT_TRUSTED_PROXY_CIDRS = "127.0.0.1/32,::1/128"


def _parse_ip_address(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _trusted_proxy_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = (
        os.getenv(TRUSTED_PROXY_CIDRS_ENV)
        or os.getenv(RISK_ENGINE_TRUSTED_PROXY_CIDRS_ENV)
        or DEFAULT_TRUSTED_PROXY_CIDRS
    )
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for item in raw.split(","):
        candidate = item.strip()
        if not candidate:
            continue
        try:
            networks.append(ipaddress.ip_network(candidate, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted_proxy(ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None) -> bool:
    if ip is None:
        return False
    return any(ip in network for network in _trusted_proxy_networks())


def get_client_ip(request: Request) -> str | None:
    peer_host = request.client.host if request.client else None
    peer_ip = _parse_ip_address(peer_host)
    if peer_ip is None:
        return peer_host[:64] if peer_host else None

    if not _is_trusted_proxy(peer_ip):
        return str(peer_ip)[:64]

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        forwarded_chain = [_parse_ip_address(item) for item in forwarded_for.split(",")]
        valid_forwarded_ips = [item for item in forwarded_chain if item is not None]
        for forwarded_ip in reversed(valid_forwarded_ips):
            if not _is_trusted_proxy(forwarded_ip):
                return str(forwarded_ip)[:64]
        if valid_forwarded_ips:
            return str(valid_forwarded_ips[0])[:64]

    real_ip = _parse_ip_address(request.headers.get("x-real-ip"))
    if real_ip is not None and not _is_trusted_proxy(real_ip):
        return str(real_ip)[:64]

    return str(peer_ip)[:64]
