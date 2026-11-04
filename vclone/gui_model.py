"""Qt-free session model behind the GUI: project load/save, step runner, log. Fully unit-testable."""
from pathlib import Path
import json

import cv2
import numpy as np

from .corners import content_corners, validate_corners, validate_size

from .cmdline import STEPS
from .project import _IMPL, _licensing, MissingInput, NotImplementedStep, Project, run_step


class SessionError(Exception):
    pass


class Session:
    def __init__(self, project=None):
        self.project = project or Project()
        self.path = None
        self.dirty = False
        self.log = []

    def _note(self, msg):
        self.log.append(msg)

    def rename(self, name):
        self.project.name = name
        self.dirty = True
        self._note(f"project renamed to {name}")

    def open(self, path):
        try:
            proj = Project.load(path)
        except (OSError, ValueError, TypeError, KeyError) as e:
            raise SessionError(f"cannot open {path}: {e}") from e
        self.project, self.path, self.dirty = proj, Path(path), False
        self._note(f"opened {path}")

    def save(self, path=None):
        target = Path(path) if path else self.path
        if target is None:
            raise SessionError("no file path: use save as")
        try:
            self.project.save(target)
        except OSError as e:
            raise SessionError(f"cannot save {target}: {e}") from e
        self.path, self.dirty = target, False
        self._note(f"saved {target}")


    def capture_camera_scan(self, output_dir, projector_size, content_size, camera_index,
                            projector_x, projector_y, settle_ms=250, warmup_frames=2,
                            confirmed=False):
        """Opt-in capture and configure only after an intact capture manifest exists."""
        if not confirmed:
            raise SessionError("physical projector display confirmation required")
        pwidth, pheight = validate_size(projector_size, max_width=1920, max_height=1080)
        cwidth, cheight = validate_size(content_size)
        target = Path(output_dir).expanduser()
        if (not str(output_dir).strip() or target.exists() or target.is_symlink()
                or not target.parent.is_dir() or target.parent.is_symlink()):
            raise SessionError("capture destination must be new under an existing regular folder")
        from . import capture
        try:
            receipt = capture.capture_opencv(
                pwidth, pheight, target, camera_index=camera_index,
                projector_x=projector_x, projector_y=projector_y,
                settle_ms=settle_ms, warmup_frames=warmup_frames, confirmed=True)
            # configure_scan also validates the output image and capture manifest.
            self.configure_scan(target, [pwidth, pheight], [cwidth, cheight])
        except (capture.CaptureError, OSError, ValueError, TypeError, SessionError) as exc:
            raise SessionError(f"capture not accepted: {exc}") from exc
        self._note(f"captured {receipt.pattern_pairs} pattern pairs; hardware acceptance NOT_VERIFIED")
        return receipt

    def configure_scan(self, directory, projector_size, content_size):
        """Configure a local camera capture directory without modifying its files."""
        pwidth, pheight = validate_size(projector_size, max_width=1920, max_height=1080)
        cwidth, cheight = validate_size(content_size)
        source = Path(directory).expanduser()
        if not source.is_dir() or source.is_symlink():
            raise SessionError("scan directory must be an existing non-symlink folder")
        first = source / "p00.png"
        if (not first.is_file() or first.is_symlink()
                or first.stat().st_size > 32 * 1024 * 1024):
            raise SessionError("scan folder needs a regular p00.png camera frame (max 32 MiB)")
        manifest = source / "capture_manifest.json"
        if manifest.exists():
            try:
                if (manifest.is_symlink() or manifest.stat().st_size > 64 * 1024):
                    raise ValueError("unsafe manifest path or size")
                meta = json.loads(manifest.read_text(encoding="utf-8"))
                if (meta.get("schema") != "kmj.graycode.capture.v1"
                        or meta.get("projector_size") != [pwidth, pheight]):
                    raise ValueError("capture manifest projector size/schema mismatch")
            except (OSError, ValueError, AttributeError, TypeError) as exc:
                raise SessionError(f"invalid capture manifest: {exc}") from exc

        new_scan = dict(self.project.scan)
        changed = (new_scan.get("dir") != str(source)
                   or new_scan.get("proj_size") != [pwidth, pheight]
                   or new_scan.get("content_size") != [cwidth, cheight])
        new_scan.update(dir=str(source), proj_size=[pwidth, pheight],
                        content_size=[cwidth, cheight])
        if changed:
            for key in ("cam_corners", "content_corners", "camera_size", "corner_image"):
                new_scan.pop(key, None)
            self.project.result = {}
            self.project.steps_done = [
                step for step in self.project.steps_done
                if step not in ("Calibrate", "Recalibrate", "Edit", "Edit MRD", "Export", "RecoverExport")
            ]
        self.project.scan = new_scan
        self.dirty = True
        self._note(f"scan setup: {source} projector {pwidth}x{pheight}, content {cwidth}x{cheight}")

    def set_camera_corners(self, points, image_size):
        """Atomically attach validated camera corners and matching content corners."""
        sc = self.project.scan
        if not all(k in sc for k in ("dir", "proj_size", "content_size")):
            raise SessionError("configure the scan folder and dimensions first")
        validated = validate_corners(points, image_size)
        cw, ch = validate_size(sc["content_size"])
        new_scan = dict(sc)
        new_scan["cam_corners"] = validated
        new_scan["content_corners"] = content_corners((cw, ch))
        new_scan["camera_size"] = list(validate_size(image_size))
        new_scan["corner_image"] = "p00.png"
        self.project.scan = new_scan
        self.project.result = {}  # previous calibration is no longer valid
        self.project.steps_done = [
            step for step in self.project.steps_done
            if step not in ("Calibrate", "Recalibrate", "Edit", "Edit MRD", "Export", "RecoverExport")
        ]
        self.dirty = True
        self._note("camera corners updated: TL, TR, BR, BL (recalibration required)")

    def preview_content(self, image_path):
        """Render a CPU-only frame; no projector/window or project-file mutation."""
        source = Path(image_path)
        if source.is_symlink() or not source.is_file():
            raise SessionError("preview image must be a regular non-symlink file")
        try:
            nbytes = source.stat().st_size
            if not 0 < nbytes <= 128 * 1024 * 1024:
                raise ValueError("preview input exceeds 128 MiB limit")
            from .project import render_frame
            frame = render_frame(self.project, source)
        except (MissingInput, ValueError, TypeError, OSError, cv2.error) as exc:
            raise SessionError(f"software preview failed: {exc}") from exc
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0):
            raise SessionError("software preview returned an unsupported frame")
        self._note("CPU preview ready; hardware_acceptance=NOT_VERIFIED")
        return frame

    def save_preview_png(self, frame, target_path):
        """Export a rendered frame exclusively, never replacing an existing owner file."""
        target = Path(target_path)
        if target.suffix.lower() != ".png":
            raise SessionError("preview output requires a .png extension")
        if target.exists() or target.is_symlink() or not target.parent.is_dir() or target.parent.is_symlink():
            raise SessionError("preview output must be a new regular path in an existing directory")
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or
                frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0):
            raise SessionError("preview frame must be a nonempty uint8 BGR image")
        try:
            ok, buf = cv2.imencode(".png", frame)
            if not ok:
                raise ValueError("failed PNG encoding")
            with target.open("xb") as handle:
                handle.write(buf.tobytes())
        except (OSError, ValueError, cv2.error) as exc:
            raise SessionError(f"cannot save preview PNG: {exc}") from exc
        self._note(f"saved CPU preview to {target}; hardware_acceptance=NOT_VERIFIED")
        return target

    def steps(self):
        """[(step name, implemented)] in command-line order."""
        return [(s, s in _IMPL and _IMPL[s] is not _licensing) for s in sorted(STEPS)]

    def run(self, step):
        try:
            run_step(self.project, step)
        except MissingInput as e:
            self._note(f"{step} failed: missing input: {e}")
            raise SessionError(f"missing input: {e}") from e
        except NotImplementedStep as e:
            self._note(f"{step} failed: not implemented")
            raise SessionError(f"not implemented: {e}") from e
        except ValueError as e:
            self._note(f"{step} failed: {e}")
            raise SessionError(str(e)) from e
        self.dirty = True
        self._note(f"{step} done")
