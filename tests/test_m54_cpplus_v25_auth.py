"""M54 CP PLUS V2.5 behavioral compatibility without copying any credentials.

Based on earlier owner-provided redacted logs: cached secure profile, standard
WSSE digest refusal, HTTPS PasswordText+Nonce acceptance, and 27 Media1
profiles, including a dimensionless MainStream token.

All requests use mocked HTTPS transport; no real camera, LAN or projectors.
"""
from __future__ import annotations

from io import BytesIO
import ssl
from urllib.error import HTTPError
from urllib.request import ProxyHandler
import xml.etree.ElementTree as ET

import pytest

from vclone import onvif_client as c


PASSWORD = "M54_TEST_ONLY_UNPUBLISHED_CREDENTIAL"
SRC = {
    "host": "192.168.43.17", "port": 443, "scheme": "https",
    "username": "owner-readonly", "password": PASSWORD,
}
URI = "https://192.168.43.17:443/onvif/device_service"
ACTION = c.DEVICE + "/GetCapabilities"


def envelope(body):
    return (
        '<s:Envelope xmlns:s="' + c.SOAP + '" xmlns:tds="' + c.DEVICE +
        '" xmlns:trt="' + c.MEDIA + '" xmlns:tt="' + c.SCHEMA +
        '"><s:Body>' + body + '</s:Body></s:Envelope>'
    ).encode("utf-8")


OK = envelope("<tds:GetCapabilitiesResponse/>")
FAULT = envelope(
    '<s:Fault><s:Code><s:Value>soap:Sender</s:Value>'
    '<s:Subcode><s:Value>ter:NotAuthorized</s:Value></s:Subcode>'
    '</s:Code><s:Reason><s:Text>Rejected</s:Text></s:Reason></s:Fault>'
)
OTHER_FAULT = envelope(
    '<s:Fault><s:Code><s:Value>soap:Receiver</s:Value></s:Code>'
    '<s:Reason><s:Text>Internal server error</s:Text></s:Reason></s:Fault>'
)


def _http_error(code, body=b""):
    return HTTPError(URI, code, "secret native HTTP details", {},
                     BytesIO(body))


class Response:
    def __init__(self, body=OK):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *_a):
        return False
    def read(self, *_a):
        return self.body


def fake_transport(monkeypatch, responses):
    sent = []
    saved_handlers = []
    class Opener:
        def open(self, req, timeout):
            assert timeout == 4
            sent.append(req.data)
            reply = responses[len(sent) - 1]
            if isinstance(reply, Exception):
                raise reply
            return Response(reply)
    def builder(*handlers):
        saved_handlers.append(handlers)
        return Opener()
    monkeypatch.setattr(c, "build_opener", builder)
    return sent, saved_handlers


def _password_type(payload):
    root = ET.fromstring(payload)
    node = root.find(".//{" + c.WSSE + "}Password")
    return node.get("Type") if node is not None else None


def test_existing_digest_and_anonymous_paths_remain_unchanged():
    digest = c._soap(ACTION, SRC["username"], PASSWORD,
                     "<tds:GetCapabilities/>")
    assert _password_type(digest) == c.DIGEST_TYPE
    assert PASSWORD.encode() not in digest
    anonymous = c._soap(ACTION, "", "", "<tds:GetCapabilities/>")
    assert _password_type(anonymous) is None
    assert c.TEXT_TYPE not in anonymous.decode()


def test_passwordtext_has_standard_type_fresh_nonce_utc_timestamp():
    a = c._soap(ACTION, "operator", PASSWORD, "<tds:GetCapabilities/>",
                password_style="text")
    b = c._soap(ACTION, "operator", PASSWORD, "<tds:GetCapabilities/>",
                password_style="text")
    assert a != b
    root = ET.fromstring(a)
    password = root.find(".//{" + c.WSSE + "}Password")
    nonce = root.find(".//{" + c.WSSE + "}Nonce")
    created = root.find(".//{" + c.WSU + "}Created")
    assert password is not None and password.get("Type") == c.TEXT_TYPE
    assert password.text == PASSWORD
    assert nonce is not None and nonce.text
    assert created is not None and created.text.endswith("Z")
    with pytest.raises(c.OnvifError, match="unsupported"):
        c._soap(ACTION, "operator", PASSWORD, "", password_style="basic")


def test_https_explicit_auth_failure_retries_once_with_passwordtext(monkeypatch):
    sent, handlers = fake_transport(monkeypatch, [_http_error(401), OK])
    assert c._post(URI, SRC, ACTION, "<tds:GetCapabilities/>") is not None
    assert len(sent) == len(handlers) == 2
    assert _password_type(sent[0]) == c.DIGEST_TYPE
    assert _password_type(sent[1]) == c.TEXT_TYPE
    assert PASSWORD.encode() not in sent[0] and PASSWORD.encode() in sent[1]
    for configured in handlers:
        assert any(isinstance(h, ProxyHandler) and h.proxies == {}
                   for h in configured)
        assert any(isinstance(h, c._NoRedirect) for h in configured)


def test_https_auth_fault_500_retries_but_non_auth_fault_does_not(monkeypatch):
    sent, _ = fake_transport(monkeypatch, [_http_error(500, FAULT), OK])
    assert c._post(URI, SRC, ACTION, "<tds:GetCapabilities/>") is not None
    assert len(sent) == 2 and _password_type(sent[1]) == c.TEXT_TYPE
    sent, _ = fake_transport(monkeypatch, [_http_error(500, OTHER_FAULT)])
    with pytest.raises(c.OnvifError, match="could not complete"):
        c._post(URI, SRC, ACTION, "<tds:GetCapabilities/>")
    assert len(sent) == 1


def test_soap_auth_fault_http_200_retries_but_other_fault_does_not(monkeypatch):
    sent, _ = fake_transport(monkeypatch, [FAULT, OK])
    assert c._post(URI, SRC, ACTION, "<tds:GetCapabilities/>") is not None
    assert len(sent) == 2 and _password_type(sent[1]) == c.TEXT_TYPE
    sent, _ = fake_transport(monkeypatch, [OTHER_FAULT])
    with pytest.raises(c.OnvifError, match="refused"):
        c._post(URI, SRC, ACTION, "<tds:GetCapabilities/>")
    assert len(sent) == 1


def test_plain_http_auth_rejection_never_downgrades_to_passwordtext(monkeypatch):
    http_source = dict(SRC, scheme="http", port=80)
    sent, _ = fake_transport(monkeypatch, [_http_error(401)])
    with pytest.raises(c.OnvifError, match="rejected authentication") as exc:
        c._post("http://192.168.43.17:80/onvif/device_service",
                http_source, ACTION, "<tds:GetCapabilities/>")
    assert len(sent) == 1
    assert _password_type(sent[0]) == c.DIGEST_TYPE
    assert PASSWORD not in str(exc.value)
    assert exc.value.__cause__ is None


def test_anonymous_https_auth_failure_never_fabricates_credentials(monkeypatch):
    anon = dict(SRC, username="", password="")
    sent, _ = fake_transport(monkeypatch, [_http_error(403)])
    with pytest.raises(c.OnvifError, match="rejected authentication"):
        c._post(URI, anon, ACTION, "<tds:GetCapabilities/>")
    assert len(sent) == 1 and _password_type(sent[0]) is None


@pytest.mark.parametrize("failure", [
    ssl.SSLError("TLS invalid and credential " + PASSWORD),
    ConnectionError("could not connect " + PASSWORD),
    _http_error(302),
    _http_error(500, b"<INVALID>"),
])
def test_https_transport_or_tls_failures_cannot_trigger_plaintext_retry(
        monkeypatch, failure):
    sent, _ = fake_transport(monkeypatch, [failure])
    with pytest.raises(c.OnvifError) as exc:
        c._post(URI, SRC, ACTION, "<tds:GetCapabilities/>")
    assert len(sent) == 1
    assert PASSWORD not in str(exc.value)
    assert "192.168.43.17" not in str(exc.value)
    assert exc.value.__cause__ is None


def test_second_https_auth_rejection_fails_closed_without_credentials(monkeypatch):
    sent, _ = fake_transport(monkeypatch, [_http_error(401), _http_error(403)])
    with pytest.raises(c.OnvifError, match="rejected authentication") as exc:
        c._post(URI, SRC, ACTION, "<tds:GetCapabilities/>")
    assert len(sent) == 2
    assert _password_type(sent[1]) == c.TEXT_TYPE
    assert PASSWORD not in str(exc.value) and exc.value.__cause__ is None


def test_bounded_legacy_v25_27_media_profiles_accept_mainstream_without_size():
    entries = ['<trt:Profiles token="MediaProfile00000"/>']
    entries += [f'<trt:Profiles token="00000_{i}"/>'
                for i in range(26)]
    body = c._parse(envelope(
        "<trt:GetProfilesResponse>" + "".join(entries) +
        "</trt:GetProfilesResponse>"))
    profiles = c._profiles(body)
    assert len(profiles) == 27
    assert c._choose_profile(profiles, None) == "MediaProfile00000"
    assert c._choose_profile(profiles, "00000_3") == "00000_3"
    # Connection candidate does not prove raw fisheye dimensions.
    assert profiles[0] == ("MediaProfile00000", 0, 0)


def test_legacy_profile_fallback_not_selected_from_arbitrary_unknown_tokens():
    with pytest.raises(c.OnvifError, match="raw-square"):
        c._choose_profile([("other-1", 0, 0), ("other-2", 0, 0)], None)
    with pytest.raises(c.OnvifError, match="ambiguous"):
        c._choose_profile([
            ("MediaProfile00000", 0, 0),
            ("MediaProfile00000", 0, 0),
        ], None)


def test_bound_onvif_media_profile_count_is_still_finite():
    entries = "".join(f'<trt:Profiles token="x{i}"/>'
                      for i in range(c.MAX_PROFILES + 1))
    body = c._parse(envelope("<trt:GetProfilesResponse>" +
                             entries + "</trt:GetProfilesResponse>"))
    with pytest.raises(c.OnvifError, match="too large"):
        c._profiles(body)


def test_legacy_mainstream_token_is_really_passed_to_getstreamuri(monkeypatch):
    profiles = "".join(
        ['<trt:Profiles token="MediaProfile00000"/>'] +
        [f'<trt:Profiles token="cfg{i}"/>' for i in range(26)]
    )
    capabilities = envelope(
        '<tds:GetCapabilitiesResponse><tds:Capabilities>'
        '<tt:Media><tt:XAddr>https://192.168.43.17/onvif/media_service'
        '</tt:XAddr></tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>'
    )
    profile_payload = envelope(
        "<trt:GetProfilesResponse>" + profiles +
        "</trt:GetProfilesResponse>")
    stream = envelope(
        '<trt:GetStreamUriResponse><trt:MediaUri>'
        '<tt:Uri>rtsp://192.168.43.17:554/one</tt:Uri>'
        '</trt:MediaUri></trt:GetStreamUriResponse>'
    )
    called = []
    def post(url, source, action, xml):
        called.append(xml)
        return c._parse((capabilities, profile_payload, stream)[len(called)-1])
    monkeypatch.setattr(c, "_post", post)
    assert c.resolve_stream_uri(SRC).startswith(
        "rtsp://owner-readonly:" + PASSWORD + "@192.168.43.17:554/one"
    )
    assert len(called) == 3
    assert "<trt:ProfileToken>MediaProfile00000</trt:ProfileToken>" in called[-1]
