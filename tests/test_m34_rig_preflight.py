"""M34 Windows desktop rig preflight without starting displays or cameras."""
import json
import sys

import pytest

from vclone import camera_sources, rig_preflight as rig
from vclone.__main__ import main


def _screens():
    # Two projectors are modeled as extended desktops only, not live devices.
    return [
        {"left": 0, "top": 0, "right": 1920, "bottom": 1080, "primary": True},
        {"left": 1920, "top": 0, "right": 3200, "bottom": 800, "primary": False},
        {"left": 3200, "top": 0, "right": 4480, "bottom": 800, "primary": False},
    ]


def test_three_extended_screens_still_requires_operator_mapping():
    report = rig.report_display_layout(_screens(), expected_projectors=2)
    assert report["desktop_displays_found"] == 3
    assert report["display_layout_gate"] == "OPERATOR_MAPPING_REQUIRED"
    assert report["projector_power_state"] == "NOT_VERIFIED"
    assert report["projector_identity"] == "NOT_VERIFIED"
    assert report["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert report["desktop_rectangles"][1]["x"] == 1920
    assert report["desktop_rectangles"][2]["x"] == 3200
    assert all(set(d) == {"display_index", "x", "y", "width", "height", "primary"}
               for d in report["desktop_rectangles"])


def test_powered_off_two_projectors_may_appear_as_one_desktop_only():
    report = rig.report_display_layout(_screens()[:1], expected_projectors=2)
    assert report["desktop_displays_found"] == 1
    assert report["display_layout_gate"] == "BLOCKED_INSUFFICIENT_EXTENDED_DESKTOPS"
    assert report["next_step"] == "CHECK_WINDOWS_EXTEND_DISPLAY_CONFIGURATION"


def test_cloned_or_overlapping_desktops_cannot_be_marked_distinct_projectors():
    screens = _screens()
    screens[2] = dict(screens[1])
    report = rig.report_display_layout(screens)
    assert report["display_layout_gate"] == "BLOCKED_MIRRORED_OR_OVERLAPPING_DESKTOPS"
    assert report["overlapping_display_pairs"] == [[1, 2]]


@pytest.mark.parametrize("invalid", [
    [],
    [{"left": 0, "top": 0, "right": 1920, "bottom": 1080,
      "primary": True}] * 17,
    [{"left": 0, "top": 0, "right": -1, "bottom": 1080,
      "primary": True}],
    [{"left": 0, "top": 0, "right": 1920, "bottom": 1080,
      "primary": 1}],
    [{"left": True, "top": 0, "right": 1920, "bottom": 1080,
      "primary": True}],
])
def test_invalid_display_layouts_fail_closed(invalid):
    with pytest.raises(rig.RigPreflightError):
        rig.report_display_layout(invalid)


def test_multiple_primary_displays_rejected():
    screens = _screens()
    screens[1]["primary"] = True
    with pytest.raises(rig.RigPreflightError, match="primary"):
        rig.report_display_layout(screens)


@pytest.mark.parametrize("count", [0, 9, True, 1.5, "2"])
def test_invalid_expected_projector_count_rejected(count):
    with pytest.raises(rig.RigPreflightError):
        rig.report_display_layout(_screens(), expected_projectors=count)


def test_camera_profile_checked_offline_without_stream_uri_leak(monkeypatch, tmp_path):
    monkeypatch.setattr(rig, "enumerate_windows_displays", _screens)
    monkeypatch.setattr(
        camera_sources.cv2, "VideoCapture",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("preflight unexpectedly opened a camera")))
    pwd = "OWNER_CAMERA_PASSWORD_PRIVATE_123"
    uri = f"rtsp://owner:{pwd}@192.0.2.100:554/live"
    source = tmp_path / "private-camera.json"
    source.write_text(json.dumps({
        "schema": "kmj.camera.source.v1", "type": "rtsp",
        "source": uri, "backend": "ffmpeg",
    }), encoding="utf-8")
    before = source.read_bytes()
    report = rig.rig_preflight(expected_projectors=2, camera_profile=source)
    printable = json.dumps(report)
    assert report["camera_profile"]["source_validation"] == "PASS"
    assert report["camera_profile"]["camera_connection"] == "NOT_TESTED"
    assert "192.0.2.100" not in printable
    assert pwd not in printable
    assert source.read_bytes() == before


def test_cli_returns_safe_json_for_unmapped_projectors(monkeypatch, capsys):
    monkeypatch.setattr(rig, "enumerate_windows_displays", _screens)
    assert main(["rig-preflight", "--expected-projectors", "2"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["display_layout_gate"] == "OPERATOR_MAPPING_REQUIRED"
    assert report["camera_profile"]["source_validation"] == "NOT_CHECKED"


def test_cli_refuses_insufficient_extended_desktop(monkeypatch, capsys):
    monkeypatch.setattr(rig, "enumerate_windows_displays",
                        lambda: _screens()[:1])
    assert main(["rig-preflight"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["display_layout_gate"].startswith("BLOCKED_")


def test_read_only_enumeration_platform_guard(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(rig.RigPreflightError, match="Windows"):
        rig.enumerate_windows_displays()
