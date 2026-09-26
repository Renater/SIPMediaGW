#!/usr/bin/env python
"""Neutron lookups shared by the OpenStack provider.

Every function here is best-effort: a lookup that cannot be satisfied returns
None rather than raising, because a configuration reference may legitimately
designate either a subnet or a network, and callers always have a fallback.
"""

import logging
from ipaddress import ip_address, ip_network

logger = logging.getLogger(__name__)


def isInSubnet(ipAddr, cidr):
    """True when `ipAddr` belongs to `cidr`, False when either cannot be parsed."""
    try:
        return ip_address(ipAddr) in ip_network(cidr, strict=False)
    except (ValueError, TypeError) as exc:
        logger.debug("CIDR match failed for %s in %s: %s", ipAddr, cidr, exc)
        return False


def findSubnet(conn, ref):
    """Look up a Neutron subnet by name or id, returning None when unresolvable."""
    if not ref:
        return None
    try:
        return conn.network.find_subnet(ref)
    except Exception as exc:
        logger.debug("Reference '%s' does not resolve to a subnet: %s", ref, exc)
        return None


def findNetwork(conn, ref):
    """Look up a Neutron network by name or id, returning None when unresolvable."""
    if not ref:
        return None
    try:
        return conn.network.find_network(ref)
    except Exception as exc:
        logger.debug("Reference '%s' does not resolve to a network: %s", ref, exc)
        return None


def resolveNetworkRef(conn, ref):
    """
    Resolve a config reference that may designate either a subnet or a network.

    Returns a (subnet, network) pair where at most one member is set: the
    network is only looked up when the reference does not match a subnet.
    """
    subnet = findSubnet(conn, ref)
    if subnet is not None:
        return subnet, None
    network = findNetwork(conn, ref)
    if ref and network is None:
        logger.warning("Reference '%s' matches no Neutron subnet nor network", ref)
    return None, network


def resolvePortIdForFixedIp(conn, server, fixedIp):
    """Find the Neutron port on `server` that owns `fixedIp`, or None."""
    if not fixedIp or not server or not getattr(server, "id", None):
        return None

    try:
        portsIter = conn.network.ports(device_id=server.id)
    except Exception as exc:
        logger.warning(
            "Cannot list ports filtered by device_id=%s, skipping port resolution: %s",
            server.id, exc,
        )
        return None

    try:
        for port in portsIter:
            for fixed in getattr(port, "fixed_ips", None) or []:
                if isinstance(fixed, dict):
                    ipAddr = (
                        fixed.get("ip_address")
                        or fixed.get("ip")
                        or fixed.get("address")
                    )
                else:
                    ipAddr = fixed
                if ipAddr == fixedIp:
                    return port.id
    except Exception as exc:
        logger.warning("Error iterating ports for server %s: %s", server.id, exc)

    return None


def extractServerIps(server, primarySubnetCidr=None, expectedNetwork=None):
    """
    Extract the (private, public) IP pair from a server's address map.

    Nova returns addresses in an arbitrary order, so the first match is kept
    rather than the last: a multi-NIC server must yield the same pair on every
    call. The private IP is selected by CIDR when `primarySubnetCidr` is known,
    and by network name otherwise.
    """
    privIp = None
    pubIp = None

    for netName, addrs in (server.addresses or {}).items():
        for addr in addrs:
            ipAddr = addr.get("addr") or addr.get("address")
            if not ipAddr:
                continue
            ipType = addr.get("OS-EXT-IPS:type") or addr.get("type")

            if ipType == "floating":
                if pubIp is None:
                    pubIp = ipAddr
            elif ipType == "fixed" and privIp is None:
                if primarySubnetCidr:
                    if isInSubnet(ipAddr, primarySubnetCidr):
                        privIp = ipAddr
                elif not expectedNetwork or netName == expectedNetwork:
                    privIp = ipAddr

    return privIp, pubIp
