"""M58 GUI capture-quality tests use only temporary files and synthetic reports."""
import os
import pytest


def qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_readonly_dialog_does_not_start_hardware_or_modify_capture(tmp_path, monkeypatch):
    qt()
    from PySide6.QtWidgets import QDialog, QMessageBox
    from vclone.capture_quality_dialog import CaptureQualityDialog
    manifest = tmp_path / "capture_manifest.json"
    manifest.write_text('{"schema":"synthetic-not-inspected-at-dialog"}')
    d = CaptureQualityDialog()
    try:
        d.folder.setText(str(tmp_path))
        before = manifest.read_bytes()
        assert d.result() != QDialog.DialogCode.Accepted
        assert not d.ok_button.isEnabled()
        d._validate()
        assert d.result() != QDialog.DialogCode.Accepted
        d.confirm.setChecked(True)
        d._validate()
        assert d.result() == QDialog.DialogCode.Accepted
        assert d.values()["directory"] == str(tmp_path)
        assert d.values()["margin"] == 20
        assert d.values()["min_valid_fraction"] == 0.3
        assert d.values()["min_axis_span"] == 0.25
        assert manifest.read_bytes() == before
        assert len(list(tmp_path.iterdir())) == 1
    finally:
        d.close()


def test_capture_dialog_refuses_missing_manifest_and_bad_optional_mask(tmp_path, monkeypatch):
    qt()
    from PySide6.QtWidgets import QDialog, QMessageBox
    from vclone.capture_quality_dialog import CaptureQualityDialog
    msgs = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_args: msgs.append(_args[-1]))
    d = CaptureQualityDialog()
    try:
        d.folder.setText(str(tmp_path))
        d.confirm.setChecked(True)
        d._validate()
        assert d.result() != QDialog.DialogCode.Accepted and msgs
        (tmp_path / "capture_manifest.json").write_text("{}")
        d.mask.setText("../outside.png")
        d._validate()
        assert d.result() != QDialog.DialogCode.Accepted
        assert len(msgs) == 2
        d.mask.clear()
        d._validate()
        assert d.result() == QDialog.DialogCode.Accepted
        assert all(str(tmp_path) not in x for x in msgs)
    finally:
        d.close()


def test_capture_quality_worker_calls_existing_M25_engine_and_emits_safe_metrics(monkeypatch):
    qt()
    from vclone import gui, capture_check
    calls = []
    def fake_check(**settings):
        calls.append(settings)
        return {
            "schema": "kmj.graycode.capture-check.v1",
            "software_capture_quality": "PASS",
            "pattern_pairs_checked": 12,
            "decoded_valid_fraction": 0.82,
            "min_pair_reliable_fraction": 0.66,
            "projector_axis_span_fraction": [0.79, 0.88],
            "hardware_acceptance": "NOT_VERIFIED",
        }
    monkeypatch.setattr(capture_check, "check_capture", fake_check)
    cfg = {"directory": "local-only",
           "margin": 20, "min_valid_fraction": 0.30,
           "min_axis_span": 0.25, "camera_mask": None,
           "fisheye_profile": None}
    worker = gui.CaptureCheckWorker(cfg)
    seen, errors = [], []
    worker.checked.connect(seen.append)
    worker.failed.connect(errors.append)
    worker.run()
    assert calls == [cfg]
    assert seen[0]["pattern_pairs_checked"] == 12
    assert seen[0]["decoded_valid_fraction"] == 0.82
    assert seen[0]["hardware_acceptance"] == "NOT_VERIFIED"
    assert errors == []


def test_capture_worker_redacts_private_paths_and_opencv_errors(monkeypatch):
    qt()
    from vclone import gui, capture_check
    def explode(**kw):
        raise RuntimeError("C:/private/camera-token/secret-capture-folder")
    monkeypatch.setattr(capture_check, "check_capture", explode)
    worker = gui.CaptureCheckWorker({"directory": "C:/private/secret"})
    errors = []
    worker.failed.connect(errors.append)
    worker.run()
    assert errors == ["CAPTURE_CHECK_FAILED"]
    assert "secret" not in repr(errors)


def test_dark_gui_capture_quality_button_runs_safe_worker(monkeypatch):
    qt()
    from PySide6.QtWidgets import QMessageBox, QPushButton, QDialog
    from vclone import gui, capture_check
    class FakeDialog:
        def __init__(self, *a, **k): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): return {"directory": "private-only"}
    class Signal:
        def __init__(self): self.callbacks=[]
        def connect(self, fn): self.callbacks.append(fn)
        def emit(self, data=None):
            for cb in self.callbacks:
                cb(data) if data is not None else cb()
    class FakeWorker:
        def __init__(self, config, parent=None):
            self._settings = config
            self.checked = Signal()
            self.failed = Signal()
            self.finished = Signal()
        def start(self):
            self.checked.emit({
                "software_capture_quality": "PASS",
                "pattern_pairs_checked": 10,
                "decoded_valid_fraction": 0.72,
                "min_pair_reliable_fraction": 0.65})
            self.finished.emit()
        def deleteLater(self): pass
        def isRunning(self): return False
    monkeypatch.setattr(gui, "CaptureQualityDialog", FakeDialog)
    monkeypatch.setattr(gui, "CaptureCheckWorker", FakeWorker)
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_k: None)
    monkeypatch.setattr(capture_check, "check_capture",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            AssertionError("real capture used in GUI test")))
    w = gui.MainWindow()
    try:
        button = next(b for b in w.findChildren(QPushButton)
                      if b.text() == "Check Capture Quality")
        menu_items = [a.text() for a in w.menuBar().actions()[1].menu().actions()]
        assert "Check captured Gray-code quality (offline)…" in menu_items
        button.click()
        assert w._capture_check_worker is None
        assert any("software screening PASS" in v for v in w.session.log)
        assert not w.session.dirty
        assert w._camera_probe_worker is None
        assert w._blend_worker is None
    finally:
        w.close()
