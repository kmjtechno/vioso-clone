"""Bounded, opt-in ONVIF WS-Discovery (no account required).

Only sends one standards-based WS-Discovery Probe over local IPv4 multicast.
No subnet sweep, unsolicited camera login, password guessing, or projector I/O.
Network access only when a user explicitly clicks Auto Detect.
"""
from __future__ import annotations

import ipaddress
import secrets
import socket
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

from .onvif_client import _PRIVATE_NETWORKS

SOAP = "http://www.w3.org/2003/05/soap-envelope"
WSD = "http://schemas.xmlsoap.org/ws/2005/04/discovery"
WSA = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
MULTICAST = ("239.255.255.250", 3702)
MAX_RESPONSE = 16384
MAX_CAMERAS = 16
MAX_DATAGRAMS = 32
DEFAULT_TIMEOUT = 1.5


class DiscoveryError(ValueError):
    """Credential- and endpoint-free public diagnostic."""


def _private_ip(value):
    try:
        address = ipaddress.IPv4Address(value)
    except (ValueError, TypeError):
        raise DiscoveryError("camera discovery returned an invalid private endpoint") from None
    if not any(address in n for n in _PRIVATE_NETWORKS):
        raise DiscoveryError("camera discovery returned an address outside the private LAN")
    return str(address)


def _endpoint(raw):
    """Reject embedded credentials, redirects, unusual path and outside hosts."""
    if not isinstance(raw, str) or not 1 <= len(raw) <= 1024:
        raise DiscoveryError("ONVIF discovery endpoint invalid")
    if any(ord(c) <= 32 or ord(c) == 127 for c in raw):
        raise DiscoveryError("ONVIF discovery endpoint invalid")
    try:
        parsed = urlsplit(raw)
        host = _private_ip(parsed.hostname)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        raise DiscoveryError("ONVIF discovery endpoint invalid") from None
    path = parsed.path
    if (parsed.scheme not in ("http", "https") or not path.startswith("/")
            or not 1 <= port <= 65535
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or "\\" in path
            or ".." in path.split("/") or "//" in path
            or len(path) > 256):
        raise DiscoveryError("ONVIF discovery returned an unsafe endpoint")
    return {"host": host, "port": port, "scheme": parsed.scheme,
            "device_path": path}


def _parse_reply(payload, sender):
    """Parse a single bounded, safe ProbeMatch from a local camera.

    The source IPv4 must match advertised endpoint. We never route discovery
    responses to a different host than the device which answered.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE:
        raise DiscoveryError("oversized ONVIF discovery reply")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise DiscoveryError("unsupported ONVIF discovery declarations")
    expected = _private_ip(sender)
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise DiscoveryError("ONVIF discovery response invalid") from None
    if root.tag != "{" + SOAP + "}Envelope":
        raise DiscoveryError("ONVIF discovery envelope invalid")
    # The ONVIF WS-Discovery 2005/04 namespace is used for both outbound
    # Probe and returned ProbeMatches. No response-to-HELLO confusion.
    matches = root.findall(".//{" + WSD + "}ProbeMatch")
    found = []
    for match in matches[:MAX_CAMERAS]:
        xaddrs = match.findtext("{" + WSD + "}XAddrs")
        if not xaddrs:
            continue
        for token in xaddrs.split()[:4]:
            try:
                endpoint = _endpoint(token)
            except DiscoveryError:
                continue
            if endpoint["host"] == expected:
                found.append(endpoint)
                break
    return found


def _probe():
    # No scopes/types filter: cameras advertising NetworkVideoTransmitter or
    # tds:Device can both answer, including older ONVIF Profile S devices.
    message_id = "urn:uuid:" + secrets.token_hex(16)
    doc = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="' + SOAP + '" xmlns:a="' + WSA +
        '" xmlns:d="' + WSD + '">'
        '<s:Header><a:Action>' + WSD + '/Probe</a:Action>'
        '<a:MessageID>' + message_id + '</a:MessageID>'
        '<a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>'
        '</s:Header><s:Body><d:Probe/></s:Body></s:Envelope>'
    )
    return doc.encode("utf-8")


def discover_cameras(*, timeout=DEFAULT_TIMEOUT):
    """One short LAN-only multicast probe; result never persisted automatically."""
    if type(timeout) not in (float, int) or not 0.2 <= timeout <= 3.0:
        raise DiscoveryError("discovery timeout out of bounds")
    found = {}
    deadline = time.monotonic() + timeout
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                           socket.IPPROTO_UDP) as sock:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            sock.settimeout(timeout)
            sock.bind(("", 0))
            sock.sendto(_probe(), MULTICAST)
            for _ in range(MAX_DATAGRAMS):
                remain = deadline - time.monotonic()
                if remain <= 0 or len(found) >= MAX_CAMERAS:
                    break
                sock.settimeout(remain)
                try:
                    packet, sender = sock.recvfrom(MAX_RESPONSE + 1)
                except socket.timeout:
                    break
                if not isinstance(sender, tuple) or not sender:
                    continue
                try:
                    cameras = _parse_reply(packet, sender[0])
                except DiscoveryError:
                    continue
                for item in cameras:
                    # Deduplicate repeated ProbeMatches for one endpoint.
                    key = (item["host"], item["port"], item["scheme"],
                           item["device_path"])
                    found[key] = item
                    if len(found) >= MAX_CAMERAS:
                        break
    except OSError:
        raise DiscoveryError("ONVIF multicast discovery unavailable on this LAN") from None
    return sorted(found.values(),
                  key=lambda x: (tuple(map(int, x["host"].split("."))),
                                 x["port"], x["device_path"]))
