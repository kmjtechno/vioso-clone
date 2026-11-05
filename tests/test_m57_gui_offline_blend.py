"""M57 offline UI: two-projector CPU export only, never actual display output."""
import os

import pytest


def qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _dialog(tmp_path):
    qt()
    from vclone.offline_blend_dialog import OfflineBlendDialog
    p1, p2, img = [tmp_path / name for name in (
        "left.json", "right.json", "content.png")]
    for p in (p1, p2, img):
        p.write_bytes(b"LOCAL_ONLY_TEST_DATA")
    d = OfflineBlendDialog()
    d._project_paths = [str(p1), str(p2)]
    d.content.setText(str(img))
    d.output.setText(str(tmp_path / "new-offline-export"))
    return d, p1, p2


def test_dialog_writes_nothing_and_requires_explicit_checkbox(tmp_path):
    qt()
    from PySide6.QtWidgets import QDialog
    d, p1, p2 = _dialog(tmp_path)
    try:
        assert d.result() != QDialog.DialogCode.Accepted
        assert not d.ok_button.isEnabled()
        before = sorted(x.name for x in tmp_path.iterdir())
        d._validate_and_accept()
        assert d.result() != QDialog.DialogCode.Accepted
        assert sorted(x.name for x in tmp_path.iterdir()) == before
    finally:
        d.close()


def test_dialog_only_accepts_two_distinct_existing_clone_files_and_new_output(
        tmp_path, monkeypatch):
    qt()
    from PySide6.QtWidgets import QDialog, QMessageBox
    d, left, right = _dialog(tmp_path)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *_a, **_kw: warnings.append("sanitized"))
    try:
        d.confirm.setChecked(True)
        d._project_paths = [str(left), str(left)]
        d._validate_and_accept()
        assert warnings == ["sanitized"]
        assert d.result() != QDialog.DialogCode.Accepted
        d._project_paths = [str(left), str(right)]
        (tmp_path / "new-offline-export").mkdir()
        d._validate_and_accept()
        assert warnings == ["sanitized", "sanitized"]
        (tmp_path / "new-offline-export").rmdir()
        d._validate_and_accept()
        assert d.result() == QDialog.DialogCode.Accepted
        sources, img, dest, gamma = d.values()
        assert len(sources) == 2 and gamma == 2.2
        assert dest == str(tmp_path / "new-offline-export")
        assert not (tmp_path / "new-offline-export").exists()
    finally:
        d.close()


def test_blend_worker_calls_existing_M14_engine_without_cameras(monkeypatch):
    qt()
    from vclone import gui, multi_output, project
    paths = ["one.json", "two.json"]
    calls = []
    def load(path):
        calls.append(("load", path))
        return project.Project(name=path)
    def export(projects, image, target, *, gamma):
        calls.append(("export", len(projects), image, target, gamma))
        return {"projectors": [{"index": 1}, {"index": 2}],
                "overlap_fraction": 0.18,
                "uncovered_fraction": 0.02}
    monkeypatch.setattr(project.Project, "load", load)
    monkeypatch.setattr(multi_output, "export_multi", export)
    worker = gui.OfflineBlendWorker(paths, "content.png", "new-export", 2.2)
    ok, bad = [], []
    worker.succeeded.connect(ok.append)
    worker.failed.connect(bad.append)
    worker.run()
    assert calls == [
        ("load", "one.json"), ("load", "two.json"),
        ("export", 2, "content.png", "new-export", 2.2)]
    assert ok == [{
        "projectors": 2, "overlap_fraction": 0.18,
        "uncovered_fraction": 0.02,
        "hardware_acceptance": "NOT_VERIFIED",
    }]
    assert not bad


def test_worker_native_backend_error_never_appears_in_signal(monkeypatch):
    qt()
    from vclone import gui, multi_output, project
    monkeypatch.setattr(project.Project, "load",
                        lambda *_a: project.Project())
    def refuse(*_a, **_kw):
        raise ValueError("rtsp://operator:PRIVATE@192.168.2.30 hidden file")
    monkeypatch.setattr(multi_output, "export_multi", refuse)
    worker = gui.OfflineBlendWorker(["a", "b"], "x", "y", 2.2)
    errors = []
    worker.failed.connect(errors.append)
    worker.run()
    assert errors == ["OFFLINE_BLEND_EXPORT_FAILED"]


def test_gui_exposes_working_offline_blend_action_without_device_activation(
        monkeypatch):
    qt()
    from PySide6.QtWidgets import QPushButton, QDialog, QMessageBox
    from vclone import gui
    from vclone import multi_output
    class FakeDialog:
        def __init__(self, *_a, **_kw): pass
        def exec(self): return QDialog.DialogCode.Accepted
        def values(self): return (["left", "right"], "photo", "new", 2.2)
    class Signal:
        def __init__(self): self.slots = []
        def connect(self, fn): self.slots.append(fn)
        def emit(self, value=None):
            for fn in self.slots:
                fn(value) if value is not None else fn()
    class FakeWorker:
        def __init__(self, *args, parent=None):
            self._input = args
            self.succeeded = Signal()
            self.failed = Signal()
            self.finished = Signal()
        def start(self):
            self.succeeded.emit({
                "projectors": 2, "overlap_fraction": 0.4,
                "uncovered_fraction": 0.01})
            self.finished.emit()
        def deleteLater(self): pass
        def isRunning(self): return False
    monkeypatch.setattr(gui, "OfflineBlendDialog", FakeDialog)
    monkeypatch.setattr(gui, "OfflineBlendWorker", FakeWorker)
    monkeypatch.setattr(QMessageBox, "information", lambda *_a, **_kw: None)
    monkeypatch.setattr(multi_output, "export_multi",
                        lambda *_a, **_kw: (_ for _ in ()).throw(
                            AssertionError("real export used during GUI-only QA")))
    window = gui.MainWindow()
    try:
        button = next(x for x in window.findChildren(QPushButton)
                      if x.text() == "Offline Blend Export")
        assert button.isEnabled()
        names = [
            item.text() for item in
            window.menuBar().actions()[1].menu().actions()]
        assert "Export offline multi-projector blend…" in names
        button.click()
        assert window._blend_worker is None
        assert any("CPU-only blend export" in v for v in window.session.log)
        assert any("hardware acceptance NOT_VERIFIED" in v
                   for v in window.session.log)
        assert window.session.dirty is False
        assert window._camera_probe_worker is None
    finally:
        window.close()
