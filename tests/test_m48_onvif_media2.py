"""M48 explicit ONVIF Media2/Profile T tests: mocked XML, no real network."""
import json

import pytest

from vclone import camera_sources, onvif_client as onvif

SECRET = "M48_NEVER_PRINT_PRIVATE_PASSWORD"
SOURCE = {
    "host": "192.168.40.22", "port": 80, "scheme": "http",
    "username": "read-only", "password": SECRET,
    "media_service": "media2",
}
NS = (
    'xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" '
    'xmlns:tr2="http://www.onvif.org/ver20/media/wsdl" '
    'xmlns:tt="http://www.onvif.org/ver10/schema"'
)
MEDIA2 = onvif.MEDIA2
SERVICES = (
    "<tds:GetServicesResponse>"
    "<tds:Service><tds:Namespace>http://www.onvif.org/ver10/device/wsdl"
    "</tds:Namespace><tds:XAddr>http://192.168.40.22/onvif/device_service"
    "</tds:XAddr></tds:Service>"
    "<tds:Service><tds:Namespace>http://www.onvif.org/ver20/media/wsdl"
    "</tds:Namespace><tds:XAddr>http://192.168.40.22/onvif/media2"
    "</tds:XAddr></tds:Service></tds:GetServicesResponse>"
)
PROFILES = (
    "<tr2:GetProfilesResponse>"
    '<tr2:Profiles token="2P-panorama"><tr2:Configurations>'
    "<tr2:VideoEncoder><tt:Resolution><tt:Width>1920</tt:Width>"
    "<tt:Height>1080</tt:Height></tt:Resolution></tr2:VideoEncoder>"
    "</tr2:Configurations></tr2:Profiles>"
    '<tr2:Profiles token="1O-raw-fisheye"><tr2:Configurations>'
    "<tr2:VideoEncoder><tt:Resolution><tt:Width>2560</tt:Width>"
    "<tt:Height>2560</tt:Height></tt:Resolution></tr2:VideoEncoder>"
    "</tr2:Configurations></tr2:Profiles>"
    "</tr2:GetProfilesResponse>"
)
STREAM = (
    "<tr2:GetStreamUriResponse>"
    "<tr2:Uri>rtsp://192.168.40.22:554/opaque-camera-path?channel=1&amp;stream=0"
    "</tr2:Uri></tr2:GetStreamUriResponse>"
)


def soap(inner):
    return onvif._parse(
        ('<soap:Envelope ' + NS + '><soap:Body>' + inner +
         '</soap:Body></soap:Envelope>').encode("utf-8")
    )


def src(**kwargs):
    return dict(SOURCE, **kwargs)


def test_media2_offline_profile_validates_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(
        onvif, "_post", lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("offline validation may not contact LAN")))
    settings = {
        "schema": camera_sources.SCHEMA, "type": "onvif",
        "source": src(), "backend": "ffmpeg",
    }
    path = tmp_path / "private-owner-onvif.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    before = path.read_bytes()
    report = camera_sources.profile_status(camera_sources.read_profile(path))
    assert report["camera_type"] == "onvif"
    assert report["camera_connection"] == "NOT_TESTED"
    assert report["no_network_or_camera_access"]
    assert all(value not in json.dumps(report) for value in (
        SECRET, SOURCE["host"], SOURCE["username"], str(path)))
    assert path.read_bytes() == before


def test_media2_explicit_only_get_services_get_profiles_all_and_get_streamuri(monkeypatch):
    called = []
    def fake_post(url, settings, action, body):
        called.append((url, settings, action, body))
        return soap((SERVICES, PROFILES, STREAM)[len(called) - 1])
    monkeypatch.setattr(onvif, "_post", fake_post)
    uri = onvif.resolve_stream_uri(SOURCE)
    assert len(called) == 3
    assert called[0][2] == onvif.DEVICE + "/GetServices"
    assert "<tds:IncludeCapability>false</tds:IncludeCapability>" in called[0][3]
    assert called[1][2] == MEDIA2 + "/GetProfiles"
    assert "<tr2:Type>All</tr2:Type>" in called[1][3]
    assert called[2][2] == MEDIA2 + "/GetStreamUri"
    assert "<tr2:Protocol>RTSP</tr2:Protocol>" in called[2][3]
    assert "<tr2:ProfileToken>1O-raw-fisheye</tr2:ProfileToken>" in called[2][3]
    assert uri.startswith("rtsp://read-only:" + SECRET + "@192.168.40.22:554/")
    assert uri.endswith("?channel=1&stream=0")
    assert all(SECRET not in item[3] for item in called)


def test_media2_explicit_token_does_not_guess_another_profile(monkeypatch):
    called = []
    def fake_post(url, settings, action, body):
        called.append(body)
        return soap((SERVICES, PROFILES, STREAM)[len(called) - 1])
    monkeypatch.setattr(onvif, "_post", fake_post)
    onvif.resolve_stream_uri(src(profile_token="2P-panorama"))
    assert "2P-panorama</tr2:ProfileToken>" in called[-1]


@pytest.mark.parametrize("value", ["media3", "Media2", "", False, 1, None, ["media2"]])
def test_nonexistent_media_service_refused_before_any_network(value, monkeypatch):
    monkeypatch.setattr(
        onvif, "_post", lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("invalid profile attempted network")))
    with pytest.raises(camera_sources.CameraSourceError):
        camera_sources.validate_profile({
            "schema": camera_sources.SCHEMA, "type": "onvif",
            "source": src(media_service=value), "backend": "ffmpeg",
        })


def test_media2_absent_or_duplicated_service_fails_closed():
    bad = soap("<tds:GetServicesResponse><tds:Service>"
               "<tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace>"
               "<tds:XAddr>http://192.168.40.22/onvif/media</tds:XAddr>"
               "</tds:Service></tds:GetServicesResponse>")
    with pytest.raises(onvif.OnvifError, match="not uniquely advertised"):
        onvif._media2_service_xaddr(bad, SOURCE)
    duplicate = soap(SERVICES.replace("</tds:GetServicesResponse>",
                           '<tds:Service><tds:Namespace>' + MEDIA2 +
                           '</tds:Namespace><tds:XAddr>'
                           'http://192.168.40.22/duplicate'
                           '</tds:XAddr></tds:Service></tds:GetServicesResponse>'))
    with pytest.raises(onvif.OnvifError, match="not uniquely advertised"):
        onvif._media2_service_xaddr(duplicate, SOURCE)


def test_media2_foreign_host_rejected_before_profile_list():
    value = SERVICES.replace("http://192.168.40.22/onvif/media2",
                             "http://192.168.40.23/onvif/media2")
    with pytest.raises(onvif.OnvifError, match="cross-host"):
        onvif._media2_service_xaddr(soap(value), SOURCE)


def test_media2_missing_encoded_video_configs_refused():
    value = ('<tr2:GetProfilesResponse><tr2:Profiles token="video-missing">'
             '</tr2:Profiles></tr2:GetProfilesResponse>')
    with pytest.raises(onvif.OnvifError, match="no bounded video"):
        onvif._media2_profiles(soap(value))


def test_media2_uses_exact_preferred_square_and_refuses_ambiguous():
    profiles = onvif._media2_profiles(soap(PROFILES))
    assert onvif._choose_profile(profiles, None) == "1O-raw-fisheye"
    assert onvif._choose_profile(profiles, "2P-panorama") == "2P-panorama"
    with pytest.raises(onvif.OnvifError, match="ambiguous"):
        onvif._choose_profile(profiles + [("other-raw", 2560, 2560)], None)


def test_media1_existing_source_remains_default_without_media2_calls(monkeypatch):
    source = {k: v for k, v in SOURCE.items() if k != "media_service"}
    calls = []
    def fake_post(url, settings, action, body):
        calls.append(action)
        assert MEDIA2 not in action
        if len(calls) == 1:
            payload = (
                "<tds:GetCapabilitiesResponse><tds:Capabilities>"
                '<tt:Media><tt:XAddr>http://192.168.40.22/onvif/media1'
                "</tt:XAddr></tt:Media></tds:Capabilities></tds:GetCapabilitiesResponse>"
            )
        elif len(calls) == 2:
            payload = (
                '<trt:GetProfilesResponse xmlns:trt="' + onvif.MEDIA + '">'
                '<trt:Profiles token="raw-legacy">'
                "<tt:VideoEncoderConfiguration><tt:Resolution>"
                "<tt:Width>2560</tt:Width><tt:Height>2560</tt:Height>"
                "</tt:Resolution></tt:VideoEncoderConfiguration>"
                "</trt:Profiles></trt:GetProfilesResponse>"
            )
        else:
            payload = '<tt:Uri>rtsp://192.168.40.22/live</tt:Uri>'
        return soap(payload)
    monkeypatch.setattr(onvif, "_post", fake_post)
    uri = onvif.resolve_stream_uri(source)
    assert len(calls) == 3
    assert uri.endswith("@192.168.40.22/live")


def test_media2_does_not_silently_fallback_to_media1(monkeypatch):
    def reject(*_args):
        raise onvif.OnvifError("ONVIF Media2 unavailable")
    monkeypatch.setattr(onvif, "_post", reject)
    with pytest.raises(onvif.OnvifError, match="Media2 unavailable"):
        onvif.resolve_stream_uri(SOURCE)


def test_media2_onvif_error_never_leaks_private_password(monkeypatch):
    from vclone import camera_sources
    def leak(*_args, **_kw):
        raise RuntimeError("untrusted camera " + SECRET + " at " + SOURCE["host"])
    monkeypatch.setattr(onvif, "_post", leak)
    with pytest.raises(camera_sources.CameraSourceError) as err:
        camera_sources.open_camera({
            "schema": camera_sources.SCHEMA, "type": "onvif",
            "source": SOURCE, "backend": "ffmpeg",
        })
    assert SECRET not in str(err.value)
    assert SOURCE["host"] not in str(err.value)
