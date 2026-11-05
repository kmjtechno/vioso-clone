"""M62 guided clean-room camera-based projector calibration wizard.

A real multi-step operator UI over existing camera, capture, geometry, mesh,
blend and export engines. Quality screening and warp solve are direct guarded
CPU actions, not cosmetic simulated stages. Hardware operation is always in
the existing explicit-consent owner dialogs.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QInputDialog, QScrollArea, QVBoxLayout, QWidget, QFrame,
)

from .gui_model import Session
from .project import Project
from .wizard_engine import (
    WizardSolveError, capture_fingerprint, inspect_capture,
    project_signature, solve_detached,
)


STAGES = (
    ("project", "Project & Surface",
     "Start or open one independent clone project for one physical projector. "
     "For two projectors, calibrate each projector into its own saved JSON."),
    ("camera", "Camera Setup",
     "Use the actual CP PLUS ONVIF camera or USB webcam. Inspect live frames "
     "and raw fisheye geometry before any projector output."),
    ("rig", "Projector Arrangement",
     "Read the Windows Extended-desktop layout, identify real physical "
     "projectors and avoid mirrored or primary displays."),
    ("capture", "Pattern Scan",
     "Capture bounded Gray-code image pairs from ONE selected physical "
     "projector after owner verification; or attach an existing capture."),
    ("quality", "Scan Quality & Fisheye",
     "Validate real captured patterns, decoded coverage and projector "
     "axis span. Optionally use a measured fisheye lens profile in the "
     "capture directory; never guess lens coefficients."),
    ("corners", "Surface Geometry",
     "Click four actual content-space corners on the camera image. "
     "When fisheye correction is enabled, points are chosen in rectified space."),
    ("solve", "Automatic Warp Solve",
     "Run independent Gray-code decoding and camera-to-content mapping "
     "on a detached project. M25 capture screening must pass first."),
    ("edit", "Refine Geometry",
     "Review the CPU warp mesh, manually adjust measured control points "
     "and inspect corrected content without opening a projector."),
    ("blend", "Two-Projector Compound",
     "Save each independently calibrated projector project. Compute "
     "overlap/edge-blend PNGs and software seam checks for both projects."),
    ("export", "Verify & Deploy",
     "Save clone JSON, review CPU output and use strictly consented timed "
     "single or multi-projector still presentation. Native VIOSO SPS and "
     "hardware optical acceptance remain separate gates."),
)


class WizardWorker(QThread):
    """One bound CPU-only action; never manipulates a live Qt Session."""

    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, operation, project, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.project = deepcopy(project)

    def run(self):
        try:
            if self.operation == "quality":
                result = inspect_capture(self.project)
            elif self.operation == "solve":
                result = solve_detached(self.project)
            else:
                raise WizardSolveError("WIZARD_UNKNOWN_ACTION")
            self.succeeded.emit(result)
        except WizardSolveError as exc:
            self.failed.emit(str(exc))
        except Exception:
            # Do not send native camera path, filenames, RTSP login or OpenCV
            # exception objects across worker/GUI boundaries.
            self.failed.emit("WIZARD_CPU_ACTION_FAILED")


class CalibrationWizard(QDialog):
    """A ten-stage live calibration workflow with explicit operator gates."""

    def __init__(self, studio, parent=None):
        super().__init__(parent or studio)
        self.studio = studio
        self.setWindowTitle("KMJ Calibration Wizard — Independent Two-Projector Workflow")
        self.setMinimumSize(1050, 690)
        self._index = 0
        self._task = None
        self._task_kind = None
        self._task_source = None
        self._task_signature = None
        self._quality = None
        self._quality_source = None
        self._build_ui()
        # Camera probe/rig actions run on the Studio, possibly asynchronously.
        # Polling only reads metadata/status labels; never accesses hardware.
        self._refresh_clock = QTimer(self)
        self._refresh_clock.setInterval(900)
        self._refresh_clock.timeout.connect(self.refresh_status)
        self._refresh_clock.start()
        self.goto(0)

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        sidebar = QFrame()
        sidebar.setObjectName("WizardSidebar")
        sidebar.setFixedWidth(258)
        side = QVBoxLayout(sidebar)
        side.setSpacing(5)
        brand = QLabel("KMJ  /  CALIBRATION")
        brand.setObjectName("WizardBrand")
        side.addWidget(brand)
        side.addWidget(QLabel("10-STEP OPERATOR WORKFLOW"))
        self.nav = []
        for index, (_, title, _) in enumerate(STAGES):
            button = QPushButton(f"{index + 1:02d}  {title}")
            button.setObjectName("WizardNav")
            button.clicked.connect(
                lambda _checked=False, at=index: self.goto(at))
            button.setMinimumHeight(36)
            side.addWidget(button)
            self.nav.append(button)
        side.addStretch(1)
        side.addWidget(QLabel("OPTICS: NOT VERIFIED\nUNSIGNED LAB BUILD"))
        root.addWidget(sidebar)

        body = QVBoxLayout()
        root.addLayout(body, 1)
        self.heading = QLabel()
        self.heading.setObjectName("WizardHeading")
        body.addWidget(self.heading)
        self.description = QLabel()
        self.description.setWordWrap(True)
        body.addWidget(self.description)
        self.status_label = QLabel()
        self.status_label.setObjectName("WizardStageStatus")
        self.status_label.setWordWrap(True)
        body.addWidget(self.status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.page_container = QWidget()
        self.page_content = QVBoxLayout(self.page_container)
        self.page_content.setContentsMargins(10, 18, 10, 12)
        self.page_content.setSpacing(12)
        scroll.setWidget(self.page_container)
        body.addWidget(scroll, 1)

        self.qa_label = QLabel()
        self.qa_label.setWordWrap(True)
        self.qa_label.setObjectName("WizardQa")
        body.addWidget(self.qa_label)

        controls = QHBoxLayout()
        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.refresh_button = QPushButton("Refresh stage status")
        self.close_button = QPushButton("Close Wizard")
        self.back_button.clicked.connect(lambda: self.goto(self._index - 1))
        self.next_button.clicked.connect(lambda: self.goto(self._index + 1))
        self.refresh_button.clicked.connect(self.refresh_status)
        self.close_button.clicked.connect(self.close)
        controls.addWidget(self.back_button)
        controls.addWidget(self.next_button)
        controls.addStretch(1)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.close_button)
        body.addLayout(controls)

        self.setStyleSheet("""
            QDialog { background: #0b111c; color: #e7eef9; }
            QFrame#WizardSidebar { background: #111c2c; border-radius: 10px; }
            QLabel#WizardBrand { color: #4edbbe; font-size: 18px; font-weight: 800; }
            QLabel#WizardHeading { color: #f6faff; font-size: 25px; font-weight: 700; }
            QLabel#WizardStageStatus { color: #4edbbe; font-size: 14px; }
            QLabel#WizardQa { color: #e4bd82; font-size: 12px; }
            QPushButton { background: #1d2c42; border: 1px solid #3c526c;
                          color: #edf5ff; padding: 8px 11px; border-radius: 7px; }
            QPushButton:disabled { color: #677991; }
            QPushButton#WizardNav { text-align: left; }
            QScrollArea { border: 0; background: transparent; }
        """)

    def _action(self, title, method, explanation):
        button = QPushButton(title)
        button.setMinimumHeight(41)
        button.setToolTip(explanation)
        button.clicked.connect(lambda _checked=False: method())
        self.page_content.addWidget(button)
        note = QLabel(explanation)
        note.setWordWrap(True)
        note.setStyleSheet("color: #a1b2c9;")
        self.page_content.addWidget(note)

    def _studio_action(self, name):
        if self._task is not None:
            return
        method = getattr(self.studio, name)
        self.hide()
        try:
            method()
        finally:
            self.show()
            self.refresh_status()

    def _add_studio(self, title, method, note):
        self._action(title, lambda: self._studio_action(method), note)

    def _clear_page(self):
        while self.page_content.count():
            item = self.page_content.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def goto(self, index):
        if self._task is not None or not 0 <= index < len(STAGES):
            return
        self._index = index
        self._clear_page()
        self.heading.setText(f"STEP {index + 1:02d}  /  {STAGES[index][1]}")
        self.description.setText(STAGES[index][2])
        stage = STAGES[index][0]
        if stage == "project":
            self._action("Create NEW isolated projector project",
                         self.create_project,
                         "Never discards dirty project data; save current project first.")
            self._add_studio("Open existing clone JSON", "open_project",
                             "Read a saved single-projector calibration.")
            self._add_studio("Save project as JSON", "save_project_as",
                             "Use a different JSON name for each projector.")
        elif stage == "camera":
            self._add_studio("Auto Detect / Connect ONVIF Camera", "probe_onvif_camera_once",
                             "Owner-approved private LAN camera, optional login, six real frames; projectors OFF.")
            self._add_studio("Test selected USB/RTSP camera profile", "probe_selected_camera",
                             "One camera-only probe after explicit consent; no projector output.")
        elif stage == "rig":
            self._add_studio("Inspect Windows display arrangement", "check_display_rig",
                             "Read-only inspection. A detected screen is NOT proof of projector identity or power.")
        elif stage == "capture":
            self._add_studio("Capture Gray-code on selected projector", "capture_camera",
                             "Physical projector activation needs independent owner confirmation. "
                             "Capture one projector at a time into a NEW folder.")
            self._add_studio("Attach existing Gray-code capture folder", "setup_scan",
                             "Import existing scan manifest/images with exact sizes, without projector output.")
        elif stage == "quality":
            self._action("Validate THIS project's Gray-code capture", self.run_quality,
                         "Real M25 quality check: all pattern PNGs, contrast, decoded valid area and axis span. "
                         "Read-only CPU worker, not a simulated pass.")
            self._action("Attach verified fisheye intrinsics JSON", self.attach_fisheye,
                         "Optional measured lens JSON stored in the capture folder; "
                         "invalidates stale corners and calibration.")
        elif stage == "corners":
            self._add_studio("Select four camera-to-content corners", "select_corners",
                             "TL, TR, BR, BL in measured/rectified image space. "
                             "Bad geometry cannot be accepted.")
        elif stage == "solve":
            self._action("Run strict quality check + automatic warp solve",
                         self.run_solve,
                         "Runs M25 screening and actual Gray-code/homography mesh calibration "
                         "off the GUI thread; commits only if project/captures are unchanged.")
        elif stage == "edit":
            self._add_studio("Edit calibrated warp mesh points", "edit_warp_mesh",
                             "Modify actual mesh nodes with bounded deltas. Cancel discards changes.")
            self._add_studio("Preview real CPU-calibrated content", "preview_content",
                             "Render the current mesh without camera, projector or disk export.")
        elif stage == "blend":
            self._add_studio("Compare two calibrated projector footprints", "compare_two_projectors",
                             "Requires a saved second project's clone JSON; checks overlap/coverage offline.")
            self._add_studio("Export combined two-projector blend PNGs", "export_offline_multi_blend",
                             "Choose both saved clone projects; exports verified per-projector stills to NEW folder.")
        else:
            self._add_studio("Save current calibrated projector JSON", "save_project_as",
                             "Independent clone JSON, not proprietary VIOSO .sps.")
            self._add_studio("Preview corrected content on this PC", "preview_content",
                             "Software-only preview; does not certify projector geometry.")
            self._add_studio("Present one calibrated still on projector", "present_calibrated_still",
                             "Owner must physically identify power-ON Extended screen and confirm twice.")
            self._add_studio("Present verified dual-projector blend stills", "present_multi_still",
                             "Uses existing M14 manifest+SHA checks and explicit per-projector mapping.")
        self.page_content.addStretch(1)
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(index + 1 < len(STAGES))
        for j, button in enumerate(self.nav):
            button.setStyleSheet(
                "border-color: #4edbbe; color: #4edbbe;" if j == index else "")
        self.refresh_status()

    def create_project(self):
        """Never silently overwrite or discard another projector's data."""
        session = self.studio.session
        if session.dirty or (session.path is None and
                (session.project.result or session.project.scan or
                 session.project.displays or session.project.steps_done)):
            QMessageBox.warning(
                self, "Project preservation",
                "Save the existing project to a separate clone JSON before "
                "creating another projector calibration.")
            return
        name, ok = QInputDialog.getText(
            self, "New projector calibration", "Project name")
        if not ok or not name.strip():
            return
        if len(name) > 120:
            QMessageBox.warning(self, "Project name", "Name is too long.")
            return
        self.studio.session = Session(Project(name=name.strip()))
        self.studio.clear_preview()
        self.studio.refresh()
        self._quality = None
        self._quality_source = None
        self.refresh_status()

    def _launch(self, kind):
        if self._task is not None:
            return
        session = self.studio.session
        try:
            signature = project_signature(session.project)
            capture_fingerprint(session.project.scan)
        except WizardSolveError as exc:
            QMessageBox.warning(self, "Calibration wizard", str(exc))
            return
        self._task_source = session.project
        self._task_signature = signature
        self._task_kind = kind
        worker = WizardWorker(kind, session.project, self)
        self._task = worker
        worker.succeeded.connect(self._task_succeeded)
        worker.failed.connect(self._task_failed)
        worker.finished.connect(self._task_finished)
        self.status_label.setText(
            "REAL CPU " + kind.upper() + " RUNNING — no device access")
        self.back_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.close_button.setEnabled(False)
        worker.start()

    def run_quality(self):
        self._launch("quality")

    def run_solve(self):
        self._launch("solve")

    def _unchanged(self, receipt):
        try:
            return (
                self.studio.session.project is self._task_source
                and project_signature(self._task_source) == self._task_signature
                and capture_fingerprint(self._task_source.scan)
                == receipt["capture_fingerprint"]
            )
        except (WizardSolveError, KeyError, ValueError, TypeError):
            return False

    def _task_succeeded(self, receipt):
        if not isinstance(receipt, dict) or not self._unchanged(receipt):
            self._quality = None
            QMessageBox.warning(
                self, "Calibration wizard",
                "WIZARD_SOURCE_CHANGED. Project/capture changed during CPU processing; "
                "no result committed. Retry with stable inputs.")
            return
        if self._task_kind == "quality":
            self._quality = dict(receipt)
            self._quality_source = self._task_signature
            self.studio.session._note(
                "wizard M25 capture software quality PASS; physical optics NOT_VERIFIED")
        elif self._task_kind == "solve":
            if (receipt.get("software_capture_quality") != "PASS"
                    or not isinstance(receipt.get("result"), dict)
                    or not receipt["result"].get("mesh")):
                self._task_failed("WIZARD_WARP_RESULT_INVALID")
                return
            session = self.studio.session
            session.project.result = receipt["result"]
            session.project.steps_done = receipt["steps_done"]
            session.dirty = True
            session._note(
                "wizard real Gray-code warp solve complete; "
                "physical projector optical acceptance NOT_VERIFIED")
            self._quality = None
            self._quality_source = None
            self.studio.clear_preview()
            self.studio.refresh()
        else:
            return
        self.qa_label.setText(
            "CPU result: " + self._task_kind.upper()
            + " PASS  ·  physical optical acceptance NOT VERIFIED")
        self.refresh_status()

    def _task_failed(self, code):
        self._quality = None
        self._quality_source = None
        allowed = {
            "WIZARD_INVALID_PROJECT", "WIZARD_SCAN_NOT_CONFIGURED",
            "WIZARD_CAPTURE_REQUIRED", "WIZARD_PROJECTOR_SIZE_REQUIRED",
            "WIZARD_CAPTURE_PROFILE_REFUSED", "WIZARD_CAPTURE_INCOMPLETE",
            "WIZARD_CAPTURE_CHANGED", "WIZARD_CAPTURE_QUALITY_FAILED",
            "WIZARD_CAPTURE_MISMATCH", "WIZARD_CORNERS_OR_SCAN_REQUIRED",
            "WIZARD_WARP_SOLVE_FAILED", "WIZARD_WARP_RESULT_INVALID",
            "WIZARD_CPU_ACTION_FAILED", "WIZARD_UNKNOWN_ACTION",
        }
        code = code if code in allowed else "WIZARD_CPU_ACTION_FAILED"
        self.qa_label.setText(
            "CPU result: " + code + " · physical optical acceptance NOT VERIFIED")
        QMessageBox.warning(
            self, "Calibration wizard", code +
            ". Check source captures, actual corners, contrast and projector sizes. "
            "No camera or projector was operated by this worker.")

    def _task_finished(self):
        if self._task is not None:
            self._task.project = None
            self._task.deleteLater()
            self._task = None
        self._task_kind = None
        self._task_source = None
        self._task_signature = None
        self.close_button.setEnabled(True)
        self.goto(self._index)

    def attach_fisheye(self):
        """Link only an existing measured profile in this capture directory."""
        if self._task is not None:
            return
        from .fisheye_rectify import read_fisheye_profile
        session = self.studio.session
        try:
            root = Path(session.project.scan["dir"])
            if root.is_symlink() or not root.is_dir():
                raise ValueError("invalid capture")
        except (KeyError, OSError, ValueError):
            QMessageBox.warning(
                self, "Fisheye profile", "Configure a real camera capture folder first.")
            return
        choice, _ = QFileDialog.getOpenFileName(
            self, "Choose measured OpenCV fisheye intrinsics within capture folder",
            str(root), "Fisheye JSON (*.json)")
        if not choice:
            return
        try:
            path = Path(choice)
            if (path.is_symlink() or path.parent.resolve(strict=True)
                    != root.resolve(strict=True)):
                raise ValueError("not a regular profile inside capture folder")
            profile = read_fisheye_profile(path)
            manifest = root / "capture_manifest.json"
            if (manifest.is_symlink() or not manifest.is_file()
                    or not 0 < manifest.stat().st_size <= 16384):
                raise ValueError("missing bounded manifest")
            recorded = json.loads(manifest.read_text(encoding="utf-8"))
            if profile["image_size"] != recorded.get("camera_size"):
                raise ValueError("lens profile resolution mismatch")
        except (OSError, ValueError, TypeError, KeyError):
            QMessageBox.warning(
                self, "Fisheye profile",
                "Measured fisheye JSON was refused. Match camera capture "
                "dimensions and use a regular profile inside the capture folder.")
            return
        name = path.name
        if session.project.scan.get("fisheye_profile") == name:
            return
        consent = QMessageBox.question(
            self, "Change lens coordinate system",
            "Use this MEASURED fisheye profile for future quality checks and "
            "warp solves? Existing camera corners, calibration mesh and export "
            "must be invalidated; pick new corners on RECTIFIED frames.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if consent != QMessageBox.StandardButton.Yes:
            return
        session.project.scan["fisheye_profile"] = name
        for key in ("cam_corners", "content_corners", "camera_size",
                    "corner_image"):
            session.project.scan.pop(key, None)
        session.project.result = {}
        session.project.steps_done = [
            step for step in session.project.steps_done
            if step not in ("Calibrate", "Recalibrate", "Edit", "Edit MRD",
                            "Export", "RecoverExport")]
        session.dirty = True
        session._note(
            "measured fisheye profile selected; stale corners/mesh invalidated")
        self._quality = None
        self._quality_source = None
        self.studio.clear_preview()
        self.studio.refresh()
        self.refresh_status()

    def _quality_current(self):
        if self._quality is None or self._quality_source is None:
            return False
        try:
            return (
                project_signature(self.studio.session.project)
                == self._quality_source
                and capture_fingerprint(self.studio.session.project.scan)
                == self._quality["capture_fingerprint"]
            )
        except (WizardSolveError, KeyError, ValueError, TypeError):
            return False

    def stage_status(self, key):
        p = self.studio.session.project
        scan = p.scan
        mesh = p.result.get("mesh")
        if key == "project":
            return ("SAVED CLONE JSON · optics unverified"
                    if self.studio.session.path is not None
                    and not self.studio.session.dirty
                    else "Save each projector's JSON before compound export")
        if key == "camera":
            return ("FRAME PROBE RECEIPT · optics unverified"
                    if self.studio.camera_status_label.text().startswith("FRAMES READ")
                    else "Camera-only operator test required")
        if key == "rig":
            return ("WINDOWS LAYOUT FOUND · physical mapping required"
                    if self.studio.display_status_label.text().startswith("DETECTED")
                    else "Two Extended projector displays not verified")
        if key == "capture":
            return ("CAPTURE CONFIGURED · image quality not yet established"
                    if scan.get("dir") and scan.get("proj_size")
                    else "Real Gray-code capture directory required")
        if key == "quality":
            return ("M25 SOFTWARE QUALITY PASS · optics unverified"
                    if self._quality_current()
                    else "Read-only Gray-code quality check required")
        if key == "corners":
            return ("FOUR CORNERS CONFIGURED · verify physical geometry"
                    if (isinstance(scan.get("cam_corners"), list)
                        and len(scan["cam_corners"]) == 4
                        and isinstance(scan.get("content_corners"), list)
                        and len(scan["content_corners"]) == 4)
                    else "Select real camera/content corners")
        if key == "solve":
            return ("SOFTWARE WARP MESH PRESENT · optics unverified"
                    if isinstance(mesh, list) and bool(mesh)
                    else "Run real quality-gated Gray-code solve")
        if key == "edit":
            return ("MANUAL NODE CHANGES PRESENT · optics unverified"
                    if p.result.get("manual_edit_nodes", 0)
                    else "Optional fine tuning after warp solve")
        if key == "blend":
            return "Save TWO calibrated JSON projects; run M14 offline blend"
        if mesh and self.studio.session.path is not None and not self.studio.session.dirty:
            return "CLONE PROJECT SAVED · physical QA and native SPS unverified"
        return "Save validated clone calibration; no hardware acceptance yet"

    def refresh_status(self):
        if self._task is not None:
            return
        key = STAGES[self._index][0]
        self.status_label.setText("CURRENT STAGE: " + self.stage_status(key))
        self.qa_label.setText(
            "Real camera/optical calibration and VIOSO 7 feature parity "
            "NOT VERIFIED. Wizard software results are not hardware acceptance.")

    def closeEvent(self, event):
        if self._task is not None:
            event.ignore()
            QMessageBox.warning(
                self, "CPU calibration running",
                "A read-only quality/warp solve is active. "
                "Close only after this bounded operation finishes.")
            return
        self._refresh_clock.stop()
        super().closeEvent(event)
