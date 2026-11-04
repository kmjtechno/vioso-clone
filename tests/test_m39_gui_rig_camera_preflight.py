"""M39 operator-friendly camera/profile and Windows rig read-only preflight."""
import json
import os

import pytest

from vclone.gui_model import Session, SessionError
from vclone import camera_sources, rig_preflight


def _source(tmp_path):
    pwd = "DO_NOT_PRINT_P520_SECRET"
    uri = "rtsp://operator:" + pwd + "@192.0.2.99:554/private"
    target = tmp_path / "private-owner-camera.json"
    target.write_text(json.dumps({
        "schema": "kmj.camera.source.v1",
        "type": "rtsp",
        "source": uri,
        "backend": "ffmpeg",
    }), encoding="utf-8")
    return target, pwd, uri


def _screens():
    return [
        {"left": 0, "top": 0, "right": 1920, "bottom": 1080, "primary": True},
        {"left": 1920, "top": 0, "right": 3200, "bottom": 800, "primary": False},
        {"left": 3200, "top": 0, "right": 4480, "bottom": 800, "primary": False},
    ]


def test_camera_profile_validation_never_opens_or_logs_private_source(tmp_path, monkeypatch):
    path, secret, uri = _source(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(camera_sources.cv2, "VideoCapture",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("camera opened without consent")))
    session = Session()
    report = session.inspect_camera_profile(path)
    assert report["source_validation"] == "PASS"
    assert report["camera_connection"] == "NOT_TESTED"
    assert report["no_network_or_camera_access"] is True
    assert report["camera_type"] == "rtsp"
    assert report["capture_backend"] == "ffmpeg"
    assert path.read_bytes() == before
    assert not session.dirty and session.path is None
    receipt = json.dumps(report) + "\n".join(session.log)
    assert all(s not in receipt for s in (secret, uri, str(path), "192.0.2.99"))


def test_camera_profile_fail_closed_without_secret_leak(tmp_path):
    path, secret, uri = _source(tmp_path)
    session = Session()
    with pytest.raises(SessionError, match="profile") as e:
        session.inspect_camera_profile(tmp_path / "missing.json")
    assert str(path) not in str(e.value)
    path.write_text(json.dumps({"schema": "wrong", "type": uri, "source": secret}))
    with pytest.raises(SessionError, match="refused") as e:
        session.inspect_camera_profile(path)
    assert all(s not in str(e.value) for s in (secret, uri, str(path)))
    assert not session.dirty and session.log == []


def test_read_only_rig_inspection_requires_operator_mapping(monkeypatch):
    monkeypatch.setattr(rig_preflight, "enumerate_windows_displays", _screens)
    session = Session()
    receipt = session.inspect_rig(expected_projectors=2)
    assert receipt["display_layout_gate"] == "OPERATOR_MAPPING_REQUIRED"
    assert receipt["desktop_displays_found"] == 3
    assert receipt["projector_identity"] == "NOT_VERIFIED"
    assert receipt["projector_power_state"] == "NOT_VERIFIED"
    assert receipt["hardware_optical_acceptance"] == "NOT_VERIFIED"
    assert "OPERATOR_MAPPING_REQUIRED" in session.log[-1]
    assert not session.dirty


def test_rig_inspection_blocks_inadequate_windows_layout(monkeypatch):
    monkeypatch.setattr(rig_preflight, "enumerate_windows_displays",
                        lambda: _screens()[:1])
    session = Session()
    receipt = session.inspect_rig(expected_projectors=2)
    assert receipt["display_layout_gate"] == "BLOCKED_INSUFFICIENT_EXTENDED_DESKTOPS"
    assert "BLOCKED_" in session.log[-1]
    with pytest.raises(SessionError, match="count"):
        session.inspect_rig(expected_projectors=9)


def test_gui_actions_offscreen_and_no_camera_projection(tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    from vclone.gui import MainWindow

    path, secret, uri = _source(tmp_path)
    monkeypatch.setattr(camera_sources.cv2, "VideoCapture",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("camera unexpectedly opened")))
    monkeypatch.setattr(rig_preflight, "enumerate_windows_displays", _screens)
    app = QApplication.instance() or QApplication([])
    session = Session()
    window = MainWindow(session)
    actions = [a.text() for a in window.menuBar().actions()[1].menu().actions()]
    assert "Check camera profile (offline)..." in actions
    assert "Check Windows projector rig (read-only)..." in actions

    messages = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **kw: messages.append(("info", a[2])))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **kw: messages.append(("warning", a[2])))
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **kw: (str(path), ""))
    try:
        window.check_camera_profile()
        assert messages[-1][0] == "info"
        assert "Camera connection: NOT TESTED" in messages[-1][1]
        assert "Physical optical acceptance: NOT VERIFIED" in messages[-1][1]
        window.check_display_rig()
        assert messages[-1][0] == "info"
        assert "OPERATOR_MAPPING_REQUIRED" in messages[-1][1]
        assert "No camera or projector was started" in messages[-1][1]
        rendered = repr(messages) + "\n".join(session.log)
        assert all(s not in rendered for s in (secret, uri, str(path), "192.0.2.99"))
        assert not session.dirty

        monkeypatch.setattr(rig_preflight, "enumerate_windows_displays",
                            lambda: _screens()[:1])
        window.check_display_rig()
        assert messages[-1][0] == "warning"
        assert "BLOCKED_INSUFFICIENT_EXTENDED_DESKTOPS" in messages[-1][1]

        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: ("", ""))
        prior = len(messages)
        window.check_camera_profile()
        assert len(messages) == prior
    finally:
        window.close()
