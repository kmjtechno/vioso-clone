"""M52 credential-free ONVIF discovery and video profile selection, offline mocks.

No real LAN packets, camera frames, images, files or projector activity.
"""
import os
import socket
import xml.etree.ElementTree as ET
from urllib.request import HTTPDigestAuthHandler, ProxyHandler

import pytest

from vclone import onvif_client as onvif, onvif_discovery as discovery
from vclone import camera_sources


CAMERA = {"host": "192.168.6.23", "port": 80, "scheme": "http",
          "username": "", "password": ""}
SOAP = onvif.SOAP
WSD = discovery.WSD
CAPS = (
    '<tds:GetCapabilitiesResponse><tds:Capabilities>'
    '<tt:Media><tt:XAddr>http://192.168.6.23/onvif/media_service</tt:XAddr>'
    '</tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>'
)
PROFILES = (
    '<trt:GetProfilesResponse>'
    '<trt:Profiles token="raw-1O"><tt:VideoEncoderConfiguration>'
    '<tt:Resolution><tt:Width>2560</tt:Width><tt:Height>2560</tt:Height>'
    '</tt:Resolution></tt:VideoEncoderConfiguration></trt:Profiles>'
    '</trt:GetProfilesResponse>'
)
STREAM = (
    '<trt:GetStreamUriResponse><trt:MediaUri>'
    '<tt:Uri>rtsp://192.168.6.23:554/native1O</tt:Uri>'
    '</trt:MediaUri></trt:GetStreamUriResponse>'
)


def soap(body):
    return (
        '<s:Envelope xmlns:s="' + SOAP + '" xmlns:tds="' + onvif.DEVICE +
        '" xmlns:trt="' + onvif.MEDIA + '" xmlns:tt="' + onvif.SCHEMA +
        '"><s:Body>' + body + '</s:Body></s:Envelope>'
    ).encode("utf-8")


def reply(host="192.168.6.23", port=80, path="/onvif/device_service"):
    return (
        '<s:Envelope xmlns:s="' + SOAP + '" xmlns:d="' + WSD + '">'
        '<s:Body><d:ProbeMatches><d:ProbeMatch><d:XAddrs>'
        'http://' + host + ':' + str(port) + path +
        '</d:XAddrs></d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>'
    ).encode("utf-8")


def profile(src=None):
    return {"schema": camera_sources.SCHEMA, "type": "onvif",
            "source": CAMERA if src is None else src, "backend": "ffmpeg"}


def test_anonymous_pair_is_valid_only_for_private_explicit_camera():
    approved = onvif.validate_source(CAMERA)
    assert approved == CAMERA
    assert camera_sources.validate_profile(profile())["type"] == "onvif"
    for change in ({"username": "one"}, {"password": "secret"}):
        with pytest.raises(onvif.OnvifError, match="both"):
            onvif.validate_source(dict(CAMERA, **change))


def test_anonymous_soap_omits_username_token_and_does_not_guess_password():
    raw = onvif._soap(onvif.DEVICE + "/GetCapabilities", "", "",
                      "<tds:GetCapabilities/>")
    root = ET.fromstring(raw)
    assert root.tag == "{" + SOAP + "}Envelope"
    assert root.find(".//{" + onvif.WSSE + "}UsernameToken") is None
    assert b"PasswordDigest" not in raw and b"<tds:GetCapabilities/>" in raw


def test_anonymous_media_uri_keeps_original_routing_without_empty_account(monkeypatch):
    calls = []
    def post(url, source, action, xml):
        calls.append((url, action, xml))
        assert source["username"] == source["password"] == ""
        return onvif._parse(soap((CAPS, PROFILES, STREAM)[len(calls) - 1]))
    monkeypatch.setattr(onvif, "_post", post)
    uri = onvif.resolve_stream_uri(CAMERA)
    assert uri == "rtsp://192.168.6.23:554/native1O"
    assert "@" not in uri and ":@" not in uri
    assert len(calls) == 3


def test_anonymous_http_never_registers_digest_handler_or_proxy(monkeypatch):
    handlers = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, *_args):
            return soap("<tds:GetCapabilitiesResponse/>")
    class Opener:
        def open(self, request, timeout):
            assert timeout == 4
            payload = request.data.decode("utf-8")
            assert "UsernameToken" not in payload
            return Response()
    def make(*args):
        handlers.extend(args)
        return Opener()
    monkeypatch.setattr(onvif, "build_opener", make)
    result = onvif._post(
        "http://192.168.6.23:80/onvif/device_service",
        CAMERA, onvif.DEVICE + "/GetCapabilities",
        "<tds:GetCapabilities/>")
    assert result is not None
    assert not any(isinstance(a, HTTPDigestAuthHandler) for a in handlers)
    assert any(isinstance(a, ProxyHandler) and a.proxies == {} for a in handlers)


def test_discovered_path_must_stay_private_and_cannot_be_cross_host():
    assert discovery._endpoint(
        "http://192.168.6.23:8080/onvif/custom_service") == {
        "host": "192.168.6.23", "port": 8080, "scheme": "http",
        "device_path": "/onvif/custom_service",
    }
    assert onvif._service_url(dict(CAMERA, port=8080,
                                   device_path="/onvif/custom_service")) == (
        "http://192.168.6.23:8080/onvif/custom_service"
    )
    for value in (
        "http://8.8.8.8/onvif", "http://127.0.0.1/onvif",
        "http://user:pass@192.168.6.23/onvif",
        "http://192.168.6.23:80/path?command=reset",
        "http://192.168.6.23/../admin",
        "http://192.168.6.23//admin",
        "http://192.168.6.23:80/onvif#fragment",
        "http://192.168.6.23:0/onvif",
        "https://example.test/onvif",
    ):
        with pytest.raises(discovery.DiscoveryError):
            discovery._endpoint(value)


def test_wsdiscovery_probe_is_standard_and_only_one_multicast_send():
    doc = discovery._probe()
    root = ET.fromstring(doc)
    assert root.tag == "{" + SOAP + "}Envelope"
    assert root.find(".//{" + WSD + "}Probe") is not None
    assert discovery.MULTICAST == ("239.255.255.250", 3702)
    assert b"UsernameToken" not in doc


def test_discovery_reply_accepts_only_same_host_private_services():
    assert discovery._parse_reply(reply(), "192.168.6.23") == [{
        "host": "192.168.6.23", "port": 80, "scheme": "http",
        "device_path": "/onvif/device_service",
    }]
    assert discovery._parse_reply(reply(), "192.168.6.24") == []
    assert discovery._parse_reply(reply(host="8.8.8.8"), "192.168.6.23") == []
    with pytest.raises(discovery.DiscoveryError):
        discovery._parse_reply(reply(), "8.8.8.8")


def test_discovery_rejects_entity_attack_and_unbounded_reply():
    with pytest.raises(discovery.DiscoveryError):
        discovery._parse_reply(
            b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///C:/secret'>]>",
            "192.168.6.23")
    with pytest.raises(discovery.DiscoveryError):
        discovery._parse_reply(b"x" * (discovery.MAX_RESPONSE + 1),
                               "192.168.6.23")


def test_one_bounded_discovery_dedupes_malformed_and_duplicate_responses(monkeypatch):
    events = []
    class FakeSock:
        packets = [
            (b"garbage", ("192.168.6.23", 3702)),
            (reply(), ("192.168.6.23", 3702)),
            (reply(), ("192.168.6.23", 3702)),
        ]
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def setsockopt(self, *args): events.append(("sockopt", args))
        def settimeout(self, value): assert 0 <= value <= 3.0
        def bind(self, address): assert address == ("", 0)
        def sendto(self, data, dest):
            assert dest == discovery.MULTICAST
            assert b"UsernameToken" not in data
            events.append(("send", dest))
        def recvfrom(self, count):
            assert count == discovery.MAX_RESPONSE + 1
            if self.packets:
                return self.packets.pop(0)
            raise socket.timeout()
    monkeypatch.setattr(discovery.socket, "socket", lambda *_: FakeSock())
    found = discovery.discover_cameras(timeout=0.5)
    assert found == discovery._parse_reply(reply(), "192.168.6.23")
    assert sum(1 for what, *_ in events if what == "send") == 1
    assert any(event[0] == "sockopt" and event[1][-1] == 1 for event in events)


def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_gui_dialog_has_discovery_button_and_requires_camera_consent(monkeypatch):
    qt_app()
    from PySide6.QtWidgets import QDialog
    from vclone.onvif_quick_dialog import OnvifQuickProbeDialog
    monkeypatch.setattr(discovery, "discover_cameras",
                        lambda: discovery._parse_reply(reply(), "192.168.6.23"))
    dlg = OnvifQuickProbeDialog()
    try:
        assert dlg.host.text() == ""
        assert dlg.username.text() == dlg.password.text() == ""
        assert dlg.profile() is None
        assert not dlg.confirm.isChecked() and not dlg.ok_button.isEnabled()
        assert "Auto Detect" in dlg.detect_button.text()
        dlg.detect_button.click()
        assert dlg.host.text() == "192.168.6.23"
        assert dlg.port.value() == 80
        assert dlg._source_profile()["source"]["device_path"] == "/onvif/device_service"
        assert not dlg.ok_button.isEnabled()
        dlg.confirm.setChecked(True)
        dlg._validate_and_accept()
        assert dlg.result() == QDialog.DialogCode.Accepted
        saved = dlg.profile()
        assert saved["source"]["username"] == saved["source"]["password"] == ""
    finally:
        dlg.clear_transient_profile()
        dlg.close()


def test_multi_camera_choice_only_selects_one_and_cancel_starts_none(monkeypatch):
    qt_app()
    from PySide6.QtWidgets import QDialog, QInputDialog
    from vclone.onvif_quick_dialog import OnvifQuickProbeDialog
    other = dict(discovery._endpoint(
        "http://192.168.6.24:8080/custom_device"))
    options = [discovery._endpoint(
        "http://192.168.6.23:80/onvif/device_service"), other]
    monkeypatch.setattr(discovery, "discover_cameras", lambda: options)
    monkeypatch.setattr(QInputDialog, "getItem", lambda *a, **k: ("", False))
    dlg = OnvifQuickProbeDialog()
    try:
        dlg.detect_button.click()
        assert dlg.host.text() == ""
        monkeypatch.setattr(QInputDialog, "getItem",
                            lambda parent, title, caption, names, index, editable:
                            (names[1], True))
        dlg.detect_button.click()
        assert dlg.host.text() == "192.168.6.24"
        assert dlg.port.value() == 8080
        assert dlg._source_profile()["source"]["device_path"] == "/custom_device"
        # Editing host must NEVER route to stale discovered custom path.
        dlg.host.setText("192.168.6.23")
        assert "device_path" not in dlg._source_profile()["source"]
    finally:
        dlg.close()


def test_gui_discovery_failure_does_not_surface_raw_exception(monkeypatch):
    qt_app()
    from PySide6.QtWidgets import QMessageBox
    from vclone.onvif_quick_dialog import OnvifQuickProbeDialog
    sensitive = "secret-token-do-not-display"
    monkeypatch.setattr(discovery, "discover_cameras",
                        lambda: (_ for _ in ()).throw(
                            RuntimeError("socket failed " + sensitive)))
    messages = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *args: messages.append(args[2]))
    dlg = OnvifQuickProbeDialog()
    try:
        dlg.detect_button.click()
        assert messages and sensitive not in repr(messages)
        assert not dlg.confirm.isChecked()
        assert dlg.profile() is None
        assert dlg.detect_button.isEnabled()
    finally:
        dlg.close()
