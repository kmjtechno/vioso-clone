"""M47 bounded ONVIF Media1 integration tests: pure mocks, no camera/LAN use."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from vclone import camera_sources as cs, onvif_client as onvif
from vclone.camera_frame_probe import CameraProbeError, camera_frame_probe
from vclone.__main__ import main


PASS = "LOCAL_ONLY_CPPLUS_SECRET_M47"
SOURCE = {
    "host": "192.168.50.8",
    "port": 80,
    "scheme": "http",
    "username": "cp+operator",
    "password": PASS,
}
SOAPS = f'xmlns:s="{onvif.SOAP}" xmlns:tds="{onvif.DEVICE}" xmlns:trt="{onvif.MEDIA}" xmlns:tt="{onvif.SCHEMA}"'
CAPS = (
    '<tds:GetCapabilitiesResponse><tds:Capabilities>'
    '<tt:Media><tt:XAddr>http://192.168.50.8/onvif/media_service</tt:XAddr>'
    '</tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>'
)
PROFILES = (
    '<trt:GetProfilesResponse>'
    '<trt:Profiles token="dewarp-2P">'
    '<tt:VideoEncoderConfiguration><tt:Resolution>'
    '<tt:Width>1920</tt:Width><tt:Height>1080</tt:Height>'
    '</tt:Resolution></tt:VideoEncoderConfiguration></trt:Profiles>'
    '<trt:Profiles token="raw-1O">'
    '<tt:VideoEncoderConfiguration><tt:Resolution>'
    '<tt:Width>2560</tt:Width><tt:Height>2560</tt:Height>'
    '</tt:Resolution></tt:VideoEncoderConfiguration></trt:Profiles>'
    '</trt:GetProfilesResponse>'
)
STREAM = (
    '<trt:GetStreamUriResponse><trt:MediaUri>'
    '<tt:Uri>rtsp://192.168.50.8:554/cam/raw?channel=1&amp;subtype=0</tt:Uri>'
    '</trt:MediaUri></trt:GetStreamUriResponse>'
)


def xml(body):
    return (
        f'<s:Envelope {SOAPS}><s:Body>{body}</s:Body></s:Envelope>'
    ).encode("utf-8")


def profile(source=None):
    return {
        "schema": cs.SCHEMA, "type": "onvif",
        "source": dict(SOURCE if source is None else source), "backend": "ffmpeg",
    }


def test_manufacturer_class_onvif_profile_is_offline_and_private(tmp_path, monkeypatch, capsys):
    path = tmp_path / "private-cpplus-onvif.json"
    path.write_text(json.dumps(profile()), encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr(
        onvif, "_post", lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("ONVIF network not allowed for offline validation")))
    monkeypatch.setattr(
        cv2, "VideoCapture", lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("camera must not be opened for profile check")))
    assert main(["camera-profile-check", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["camera_type"] == "onvif"
    assert report["camera_connection"] == "NOT_TESTED"
    assert report["no_network_or_camera_access"] is True
    assert all(x not in json.dumps(report) for x in (
        PASS, SOURCE["host"], SOURCE["username"], str(path)))
    assert before == path.read_bytes()


@pytest.mark.parametrize("host", [
    "127.0.0.1", "0.0.0.0", "169.254.1.20", "8.8.8.8",
    "192.0.2.10", "localhost", "camera.example.net", "::1",
    "192.168.50.8@evil.example", "192.168.50.8/path",
])
def test_only_explicit_rfc1918_ipv4_is_allowed(host):
    src = dict(SOURCE, host=host)
    with pytest.raises(onvif.OnvifError):
        cs.validate_profile(profile(src))


@pytest.mark.parametrize("change", [
    {"scheme": "ftp"}, {"port": 0}, {"port": True},
    {"username": ""}, {"password": ""},
    {"profile_token": "bad token"}, {"host": 12345},
    {"password": "abc\nxyz"}, {"extraneous_key": "anything"},
])
def test_invalid_onvif_profiles_fail_before_camera(change):
    with pytest.raises(onvif.OnvifError):
        cs.validate_profile(profile(dict(SOURCE, **change)))


def test_media1_getprofiles_selects_original_square_instead_of_dewarp(monkeypatch):
    called = []
    def fake_post(url, source, action, body):
        called.append((url, action, body))
        return onvif._parse(xml((CAPS, PROFILES, STREAM)[len(called) - 1]))
    monkeypatch.setattr(onvif, "_post", fake_post)
    uri = onvif.resolve_stream_uri(SOURCE)
    assert len(called) == 3
    assert "GetCapabilities" in called[0][1]
    assert "GetProfiles" in called[1][1]
    assert "GetStreamUri" in called[2][1]
    assert "<trt:ProfileToken>raw-1O</trt:ProfileToken>" in called[2][2]
    assert uri.startswith("rtsp://cp%2Boperator:" + PASS + "@192.168.50.8:554/cam/raw")
    assert uri.endswith("?channel=1&subtype=0")
    assert all(PASS not in item[2] for item in called)


def test_explicit_profile_token_overrides_auto_square_choice(monkeypatch):
    source = dict(SOURCE, profile_token="dewarp-2P")
    called = []
    def fake_post(url, src, action, request):
        called.append(request)
        return onvif._parse(xml((CAPS, PROFILES, STREAM)[len(called) - 1]))
    monkeypatch.setattr(onvif, "_post", fake_post)
    onvif.resolve_stream_uri(source)
    assert "dewarp-2P</trt:ProfileToken>" in called[-1]


def test_missing_or_ambiguous_square_requires_explicit_profile_token():
    p = onvif._profiles(onvif._parse(xml(PROFILES)))
    assert onvif._choose_profile(p, None) == "raw-1O"
    assert onvif._choose_profile(p, "dewarp-2P") == "dewarp-2P"
    with pytest.raises(onvif.OnvifError, match="not found"):
        onvif._choose_profile(p, "unavailable")
    with pytest.raises(onvif.OnvifError, match="ambiguous"):
        onvif._choose_profile(p + [("duplicate-raw", 2560, 2560)], None)
    with pytest.raises(onvif.OnvifError, match="no raw-square"):
        onvif._choose_profile([("panorama", 1920, 1080)], None)


@pytest.mark.parametrize("uri", [
    "rtsp://192.168.50.9/foreign",
    "rtsp://127.0.0.1/localhost",
    "rtsp://cpoperator:leak@192.168.50.8:554/test",
    "http://192.168.50.8/stream",
    "rtsp://192.168.50.8:554/test#fragment",
    "rtsp://192.168.50.8:0/test",
])
def test_onvif_discovered_stream_cannot_redirect_to_another_host(uri):
    with pytest.raises(onvif.OnvifError):
        onvif._same_host_url(uri, SOURCE, schemes={"rtsp", "rtsps"})


def test_soap_wsse_uses_per_request_nonce_digest_and_not_password():
    one = onvif._soap("action", SOURCE["username"], PASS, "<trt:GetProfiles/>")
    two = onvif._soap("action", SOURCE["username"], PASS, "<trt:GetProfiles/>")
    assert one != two
    assert PASS.encode() not in one and PASS.encode() not in two
    assert b"PasswordDigest" in one
    assert b"UsernameToken" in one
    assert b"<wsu:Created>" in one
    assert b"cp+operator" in one
    assert onvif._parse(one) is not None


@pytest.mark.parametrize("payload", [
    b"<!DOCTYPE x [<!ENTITY x SYSTEM 'file:///etc/passwd'>]>",
    b"x" * (onvif.MAX_XML_BYTES + 1),
    b"<not-soap/>",
    xml('<s:Fault><s:Reason>permission denied</s:Reason></s:Fault>'),
])
def test_malicious_or_invalid_soap_responses_fail_closed(payload):
    with pytest.raises(onvif.OnvifError):
        onvif._parse(payload)


def test_camera_engine_uses_onvif_uri_only_after_explicit_open(monkeypatch):
    calls = []
    class FakeStream:
        def __init__(self):
            self.released = False
        def isOpened(self): return True
        def release(self): self.released = True
    stream = FakeStream()
    monkeypatch.setattr(onvif, "resolve_stream_uri",
                        lambda source: "rtsp://private_user:private_pass@192.168.50.8:554/live")
    monkeypatch.setattr(cs.cv2, "VideoCapture",
                        lambda *args: (calls.append(args), stream)[1])
    actual = cs.open_camera(profile())
    assert actual is stream
    assert len(calls) == 1
    assert calls[0][1] == cv2.CAP_FFMPEG
    assert len(calls[0][2]) == 4
    assert cv2.CAP_PROP_OPEN_TIMEOUT_MSEC in calls[0][2]
    assert cv2.CAP_PROP_READ_TIMEOUT_MSEC in calls[0][2]
    actual.release()
    assert stream.released


def test_no_consent_never_runs_onvif_resolution(tmp_path, monkeypatch):
    path = tmp_path / "private-onvif.json"
    path.write_text(json.dumps(profile()), encoding="utf-8")
    monkeypatch.setattr(onvif, "resolve_stream_uri",
                        lambda *_: (_ for _ in ()).throw(
                            AssertionError("ONVIF accessed without consent")))
    with pytest.raises(CameraProbeError, match="confirm-camera"):
        camera_frame_probe(path, confirmed=False)
    from vclone import capture
    with pytest.raises(capture.CaptureError, match="confirmation"):
        capture.capture_opencv(8, 6, tmp_path / "new-dir", camera_index=0,
                               projector_x=1920, projector_y=0,
                               camera_profile_path=path, confirmed=False)
    assert not (tmp_path / "new-dir").exists()


def test_auth_failure_scrubs_onvif_local_secret(monkeypatch):
    def fail(*_args):
        raise RuntimeError("HTTP error " + PASS + " at " + SOURCE["host"])
    monkeypatch.setattr(onvif, "_post", fail)
    # Lower-level caller intentionally sanitizes third-party ONVIF backend.
    with pytest.raises(cs.CameraSourceError) as err:
        cs.open_camera(profile())
    assert PASS not in str(err.value)
    assert SOURCE["host"] not in str(err.value)


def test_http_redirects_are_rejected_instead_of_followed():
    with pytest.raises(onvif.OnvifError, match="redirect refused"):
        onvif._NoRedirect().redirect_request(None, None, None, None, None, None)


def test_profile_status_never_contains_secret_or_source_dict():
    report = cs.profile_status(profile())
    assert "source" not in report
    assert PASS not in repr(report)
    assert SOURCE["host"] not in repr(report)
    assert report["camera_type"] == "onvif"
    assert report["camera_connection"] == "NOT_TESTED"


def test_camera_opencv_probe_redacts_credential_url_on_native_exception(monkeypatch):
    def fail(*_args, **_kw):
        raise RuntimeError("native camera error: " + PASS + "@" + SOURCE["host"])
    monkeypatch.setattr(onvif, "resolve_stream_uri", fail)
    with pytest.raises(cs.CameraSourceError) as err:
        cs.open_camera(profile())
    assert PASS not in str(err.value)
    assert SOURCE["host"] not in str(err.value)
