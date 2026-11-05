"""Minimal owner-opt-in ONVIF Media1 reader for a single private-LAN camera.

Supports ONVIF GetCapabilities -> GetProfiles -> GetStreamUri using WS-Security
UsernameToken (PasswordDigest) and HTTP Digest challenge. No WS-Discovery,
LAN scanning, arbitrary URLs, service redirects, camera configuration changes,
files or telemetry. Every error deliberately omits credentials/host/RTSP path.

Profile S Media1 only; Profile T Media2, TLS trust and firmware quirks require
separate empirical qualification. The returned URI is for local OpenCV only.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import secrets
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.error import HTTPError
from urllib.request import (
    build_opener, HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm,
    HTTPRedirectHandler, ProxyHandler, Request,
)
from xml.sax.saxutils import escape

SOAP = "http://www.w3.org/2003/05/soap-envelope"
DEVICE = "http://www.onvif.org/ver10/device/wsdl"
MEDIA = "http://www.onvif.org/ver10/media/wsdl"
SCHEMA = "http://www.onvif.org/ver10/schema"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
DIGEST_TYPE = WSSE.replace("wssecurity-secext-1.0.xsd", "username-token-profile-1.0") + "#PasswordDigest"
TEXT_TYPE = WSSE.replace("wssecurity-secext-1.0.xsd", "username-token-profile-1.0") + "#PasswordText"
NONCE_TYPE = WSSE.replace("wssecurity-secext-1.0.xsd", "soap-message-security-1.0") + "#Base64Binary"
MAX_XML_BYTES = 128 * 1024
MAX_PROFILES = 64
DEFAULT_DEVICE_PATH = "/onvif/device_service"
_PRIVATE_NETWORKS = tuple(ipaddress.ip_network(cidr) for cidr in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


# The camera layer imports ONVIF lazily only after CameraSourceError is defined.
# Preserve the public camera-source error contract for all existing callers.
from .camera_sources import CameraSourceError


class OnvifError(CameraSourceError):
    """Safe public diagnostic; never include the private camera source."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise OnvifError("ONVIF device redirect refused")


def validate_source(source):
    """Pure OFFLINE schema check; accept explicit RFC1918 IPv4 only."""
    if not isinstance(source, dict):
        raise OnvifError("ONVIF source must be a private endpoint record")
    keys = {"host", "port", "scheme", "username", "password"}
    if not keys.issubset(source) or set(source) - keys - {"profile_token", "device_path"}:
        raise OnvifError("invalid ONVIF endpoint profile keys")
    try:
        address = ipaddress.IPv4Address(source["host"])
    except (ValueError, TypeError, KeyError):
        raise OnvifError("ONVIF endpoint must use private IPv4") from None
    if not any(address in network for network in _PRIVATE_NETWORKS):
        raise OnvifError("ONVIF endpoint must be on the private LAN")
    if source["scheme"] not in ("http", "https"):
        raise OnvifError("ONVIF control requires HTTP or verified HTTPS")
    if type(source["port"]) is not int or not 1 <= source["port"] <= 65535:
        raise OnvifError("ONVIF control port must be in 1..65535")
    for field, length in (("username", 128), ("password", 512)):
        value = source[field]
        if (not isinstance(value, str) or len(value) > length
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise OnvifError("invalid private ONVIF credential") from None
    # Anonymous ONVIF on owner LAN is valid only when BOTH are blank.
    # Never silently try a half-configured account.
    if bool(source["username"]) != bool(source["password"]):
        raise OnvifError("ONVIF username and password must both be supplied or blank")
    path = source.get("device_path", DEFAULT_DEVICE_PATH)
    if (not isinstance(path, str) or not 1 <= len(path) <= 256
            or not path.startswith("/") or "//" in path
            or ".." in path.split("/") or "\\" in path
            or any(ord(c) <= 32 or ord(c) == 127 for c in path)
            or "?" in path or "#" in path):
        raise OnvifError("ONVIF discovered device path invalid")
    token = source.get("profile_token")
    if token is not None and (
        not isinstance(token, str)
        or not 1 <= len(token) <= 128
        or any(ord(c) < 33 or ord(c) > 126 for c in token)
    ):
        raise OnvifError("ONVIF profile token must be a printable opaque identifier")
    # Return a copy for the caller, never a status/report/exception.
    return dict(source)


def _same_host_url(url, source, *, schemes):
    """Accept only camera-owned URLs, no redirects, credentials or fragments."""
    if not isinstance(url, str) or not 1 <= len(url) <= 2048:
        raise OnvifError("ONVIF returned an invalid endpoint or stream URL")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except (ValueError, TypeError):
        raise OnvifError("ONVIF returned a malformed endpoint or stream URL") from None
    if (parsed.scheme not in schemes or parsed.hostname != source["host"]
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or not parsed.path.startswith("/")
            or port == 0 or any(ord(ch) < 33 or ord(ch) == 127 for ch in url)):
        raise OnvifError("ONVIF returned a cross-host or unsafe stream endpoint")
    return parsed


def _soap(action, username, password, inner_xml, *, password_style="digest"):
    """Only explicitly requested PasswordText over a caller-verified HTTPS URL.

    Defaults to standard WSSE PasswordDigest even for existing callers.
    """
    if password_style not in ("digest", "text"):
        raise OnvifError("unsupported ONVIF authentication mode")
    header = ""
    if username or password:
        nonce = secrets.token_bytes(20)
        created = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        digest = base64.b64encode(hashlib.sha1(
            nonce + created.encode("utf-8") + password.encode("utf-8")
        ).digest()).decode("ascii")
        token = base64.b64encode(nonce).decode("ascii")
        # Even PasswordText uses a fresh nonce and UTC Created timestamp.
        mode_type = DIGEST_TYPE if password_style == "digest" else TEXT_TYPE
        password_value = digest if password_style == "digest" else escape(password)
        header = (
            '<wsse:Security soap:mustUnderstand="1">'
            '<wsse:UsernameToken>'
            '<wsse:Username>' + escape(username) + '</wsse:Username>'
            '<wsse:Password Type="' + mode_type + '">' + password_value + '</wsse:Password>'
            '<wsse:Nonce EncodingType="' + NONCE_TYPE + '">' + token + '</wsse:Nonce>'
            '<wsu:Created>' + created + '</wsu:Created>'
            '</wsse:UsernameToken></wsse:Security>'
        )
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap:Envelope xmlns:soap="' + SOAP + '" xmlns:tds="' + DEVICE +
        '" xmlns:trt="' + MEDIA + '" xmlns:tt="' + SCHEMA +
        '" xmlns:wsse="' + WSSE + '" xmlns:wsu="' + WSU + '">'
        '<soap:Header>' + header + '</soap:Header><soap:Body>'
        + inner_xml + '</soap:Body></soap:Envelope>'
    )
    return envelope.encode("utf-8")


def _parse(payload):
    if not isinstance(payload, bytes) or len(payload) > MAX_XML_BYTES:
        raise OnvifError("ONVIF SOAP response outside bounded size")
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise OnvifError("ONVIF SOAP document contains unsupported declarations")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        raise OnvifError("ONVIF returned malformed SOAP") from None
    if root.tag != "{" + SOAP + "}Envelope":
        raise OnvifError("ONVIF SOAP envelope mismatch")
    body = root.find("{" + SOAP + "}Body")
    if body is None or body.find("{" + SOAP + "}Fault") is not None:
        raise OnvifError("ONVIF device refused authenticated media request")
    return body


class _AuthenticationRefused(Exception):
    """Internal control flow only. Never expose untrusted camera responses."""


def _auth_fault(payload):
    """Accept only explicit ONVIF/WS-Security authentication SOAP faults."""
    if not isinstance(payload, bytes) or len(payload) > MAX_XML_BYTES:
        return False
    upper = payload.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        return False
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return False
    if root.tag != "{" + SOAP + "}Envelope":
        return False
    body = root.find("{" + SOAP + "}Body")
    fault = body.find("{" + SOAP + "}Fault") if body is not None else None
    if fault is None:
        return False
    # Compare only short known fault-code tokens, never log a firmware
    # Reason/Text or a credential-bearing XML payload.
    allowed = {"NotAuthorized", "FailedAuthentication", "InvalidSecurity"}
    for node in fault.iter():
        if node.tag.rsplit("}", 1)[-1] not in ("Value", "Subcode"):
            continue
        text = (node.text or "").strip().rsplit(":", 1)[-1]
        if text in allowed:
            return True
    return False


def _post(url, source, action, xml):
    """Authenticated ONVIF read-only media request with bounded HTTPS retry.

    V2.5 physical logs demonstrated a subset of CP PLUS firmware rejecting
    WSSE PasswordDigest and accepting PasswordText + Nonce + Created over
    HTTPS. Retry once only for explicit auth rejection on certificate-
    verified HTTPS, using existing owner-supplied credentials.
    """
    _same_host_url(url, source, schemes={source["scheme"]})
    has_login = bool(source["username"] and source["password"])

    def send(password_style):
        handlers = [ProxyHandler({}), _NoRedirect()]
        if has_login:
            password_mgr = HTTPPasswordMgrWithDefaultRealm()
            password_mgr.add_password(
                None, url, source["username"], source["password"])
            handlers.append(HTTPDigestAuthHandler(password_mgr))
        opener = build_opener(*handlers)
        request = Request(
            url,
            data=_soap(action, source["username"], source["password"], xml,
                       password_style=password_style),
            headers={
                "Content-Type": 'application/soap+xml; charset=utf-8; action="' +
                                action + '"',
                "Accept": "application/soap+xml",
            },
            method="POST",
        )
        try:
            with opener.open(request, timeout=4) as response:
                data = response.read(MAX_XML_BYTES + 1)
        except HTTPError as exc:
            try:
                data = exc.read(MAX_XML_BYTES + 1)
            except Exception:
                data = b""
            # 401/403 HTTP auth rejection, or 500 carrying a recognized
            # SOAP authentication fault. Never retry other server failures.
            if exc.code in (401, 403) or (exc.code == 500 and _auth_fault(data)):
                raise _AuthenticationRefused() from None
            raise OnvifError(
                "ONVIF selected camera could not complete media request") from None
        except OnvifError:
            raise
        except Exception:
            # urllib and native SSL exceptions may contain private URLs,
            # hostnames and credentials. Never propagate their text or chain.
            raise OnvifError(
                "ONVIF selected camera could not complete media request") from None
        if _auth_fault(data):
            raise _AuthenticationRefused()
        return _parse(data)

    try:
        return send("digest")
    except _AuthenticationRefused:
        if source["scheme"] != "https" or not has_login:
            raise OnvifError(
                "ONVIF selected camera rejected authentication") from None
        # Never downgrade to PasswordText on HTTP, on redirect, a foreign
        # endpoint, failed TLS validation, or malformed/non-auth SOAP.
        try:
            return send("text")
        except _AuthenticationRefused:
            raise OnvifError(
                "ONVIF selected camera rejected authentication") from None


def _service_url(source):
    return (
        source["scheme"] + "://" + source["host"] + ":" +
        str(source["port"]) + source.get("device_path", DEFAULT_DEVICE_PATH)
    )


def _capabilities_xaddr(body, source):
    node = body.find(".//{" + SCHEMA + "}Media/{" + SCHEMA + "}XAddr")
    # Some firmware uses a different prefix, not a different namespace; ET
    # searches using expanded namespace names.
    if node is None or not node.text:
        raise OnvifError("ONVIF Media1 capability missing")
    value = node.text.strip()
    _same_host_url(value, source, schemes={source["scheme"]})
    return value


def _profiles(body):
    profiles = body.findall(".//{" + MEDIA + "}Profiles")
    if not 1 <= len(profiles) <= MAX_PROFILES:
        raise OnvifError("ONVIF profile list missing or too large")
    choices = []
    for node in profiles:
        token = node.attrib.get("token")
        if (not token or len(token) > 128
                or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            continue
        res = node.find(".//{" + SCHEMA + "}VideoEncoderConfiguration/{" + SCHEMA + "}Resolution")
        # Older CP PLUS firmware can advertise a valid MediaProfile token
        # but omit encoder dimensions in GetProfiles (legacy V2.5 observed
        # this). Preserve it for EXPLICIT selection or narrow main-stream
        # fallback; never label missing dimensions as a raw fisheye mode.
        w = h = 0
        if res is not None:
            try:
                w = int(res.findtext("{" + SCHEMA + "}Width") or "")
                h = int(res.findtext("{" + SCHEMA + "}Height") or "")
            except ValueError:
                w = h = 0
        if not (64 <= w <= 4096 and 64 <= h <= 4096
                and w * h <= 4096 * 2160):
            w = h = 0
        choices.append((token, w, h))
    if not choices:
        raise OnvifError("ONVIF camera has no supported bounded video profile")
    return choices


def _choose_profile(profiles, requested):
    if requested is not None:
        chosen = [p for p in profiles if p[0] == requested]
        if len(chosen) != 1:
            raise OnvifError("selected ONVIF media profile not found")
        return chosen[0][0]
    # For fisheye calibration, do NOT silently select a panorama/substream.
    # Require exactly one largest square resolution (often 2560x2560 on CP+).
    square = [p for p in profiles if p[1] >= 64 and p[1] == p[2]]
    if not square:
        # V2.5 evidence: CP PLUS returned 27 Media1 entries, most without
        # dimensions, but the real MainStream token MediaProfile00000
        # yielded a stream URI. This is a connection-only candidate and
        # never attests raw 1O fisheye optical geometry.
        legacy = [p for p in profiles if p[0] == "MediaProfile00000"]
        if len(legacy) == 1:
            return legacy[0][0]
        if len(legacy) > 1:
            raise OnvifError("ambiguous ONVIF legacy main-stream profile; set profile_token locally")
        raise OnvifError("no raw-square ONVIF profile; set profile_token locally")
    largest = max(p[1] for p in square)
    preferred = [p for p in square if p[1] == largest]
    if len(preferred) != 1:
        raise OnvifError("ambiguous ONVIF square profiles; set profile_token locally")
    return preferred[0][0]


def resolve_stream_uri(source):
    """ONVIF Media1 read-only URI resolution for one selected private camera.

    Called only after the higher-level user-approved camera probe/capture.
    No ONVIF camera configuration methods are issued.
    """
    source = validate_source(source)
    device_url = _service_url(source)
    body = _post(
        device_url, source, DEVICE + "/GetCapabilities",
        "<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>",
    )
    media_url = _capabilities_xaddr(body, source)
    body = _post(media_url, source, MEDIA + "/GetProfiles", "<trt:GetProfiles/>")
    token = _choose_profile(_profiles(body), source.get("profile_token"))
    xml = (
        "<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>"
        "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport>"
        "</trt:StreamSetup><trt:ProfileToken>" + escape(token) +
        "</trt:ProfileToken></trt:GetStreamUri>"
    )
    body = _post(media_url, source, MEDIA + "/GetStreamUri", xml)
    uri = body.findtext(".//{" + SCHEMA + "}Uri")
    if not uri:
        # Media2 is deliberately not guessed as Media1.
        raise OnvifError("ONVIF Media1 did not return an RTSP stream URI")
    parsed = _same_host_url(uri.strip(), source, schemes={"rtsp", "rtsps"})
    # For an anonymous camera, preserve the camera-provided same-host stream
    # URI WITHOUT inserting an empty user:password@ into the RTSP authority.
    if not source["username"]:
        return urlunsplit((parsed.scheme, parsed.netloc,
                           parsed.path, parsed.query, ""))
    user = quote(source["username"], safe="")
    password = quote(source["password"], safe="")
    # Only OpenCV receives these credentials, never project logs or reports.
    netloc = user + ":" + password + "@" + parsed.netloc
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))
