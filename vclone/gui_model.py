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
                            confirmed=False, camera_profile_path=None):
        """Opt-in capture, including selected private M33 source profile if requested.

        Private stream URLs/credentials and owner profile path are never logged.
        """
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
                settle_ms=settle_ms, warmup_frames=warmup_frames, confirmed=True,
                camera_profile_path=camera_profile_path)
            # configure_scan also validates the output image and capture manifest.
            self.configure_scan(target, [pwidth, pheight], [cwidth, cheight])
        except (capture.CaptureError, OSError, ValueError, TypeError, SessionError) as exc:
            if camera_profile_path is not None:
                # A third-party camera backend may embed the RTSP URI/password
                # inside an exception. Refuse to log any underlying error.
                raise SessionError(
                    "capture not accepted: selected private camera source or "
                    "projector capture failed; optical acceptance NOT_VERIFIED") from None
            raise SessionError(f"capture not accepted: {exc}") from exc
        except Exception:
            if camera_profile_path is not None:
                raise SessionError(
                    "capture not accepted: selected private camera source or "
                    "projector capture failed; optical acceptance NOT_VERIFIED") from None
            raise
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
            for key in ("cam_corners", "content_corners", "camera_size",
                        "corner_image", "corner_reference_space"):
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
        new_scan["corner_reference_space"] = (
            "rectified_fisheye" if new_scan.get("fisheye_profile") else "raw")
        self.project.scan = new_scan
        self.project.result = {}  # previous calibration is no longer valid
        self.project.steps_done = [
            step for step in self.project.steps_done
            if step not in ("Calibrate", "Recalibrate", "Edit", "Edit MRD", "Export", "RecoverExport")
        ]
        self.dirty = True
        self._note("camera corners updated: TL, TR, BR, BL (recalibration required)")


    def apply_manual_mesh(self, proposed):
        """Atomically apply bounded user-selected mesh nodes (no hardware I/O).

        The editor owns a detached mesh copy and calls this ONLY after Save.
        Reject altered topology, unobserved nodes, non-finite values and
        unexpectedly large edits. Recompute software coverage before commit.
        """
        from . import calib
        from .corners import validate_size

        current = self.project.result.get("mesh")
        if (not isinstance(current, list) or not 2 <= len(current) <= 65
                or not isinstance(proposed, list) or len(proposed) != len(current)):
            raise SessionError("manual mesh requires an existing bounded calibration")
        columns = len(current[0]) if isinstance(current[0], list) else 0
        if not 2 <= columns <= 65:
            raise SessionError("manual warp mesh columns outside bounds")
        try:
            content_size = validate_size(self.project.scan["content_size"])
        except (ValueError, KeyError, TypeError):
            raise SessionError("calibration content size missing or invalid") from None

        def parse(node):
            if (node is None or isinstance(node, (list, tuple))
                    and len(node) == 2 and node[0] is None and node[1] is None):
                return None
            if (not isinstance(node, (list, tuple)) or len(node) != 2
                    or any(isinstance(value, bool) or not isinstance(value, (int, float))
                           for value in node)):
                raise SessionError("manual warp node contains invalid coordinates")
            x, y = float(node[0]), float(node[1])
            if not np.isfinite(x) or not np.isfinite(y):
                raise SessionError("manual warp node contains non-finite coordinates")
            return [x, y]

        committed = []
        changed = 0
        for old_row, new_row in zip(current, proposed):
            if (not isinstance(old_row, list) or not isinstance(new_row, list)
                    or len(old_row) != columns or len(new_row) != columns):
                raise SessionError("manual mesh topology cannot change")
            out_row = []
            for before, after in zip(old_row, new_row):
                source, target = parse(before), parse(after)
                if (source is None) != (target is None):
                    raise SessionError("unobserved warp nodes cannot be created or deleted")
                if source is None:
                    out_row.append([None, None])
                    continue
                dx, dy = target[0] - source[0], target[1] - source[1]
                if abs(dx) > 64 or abs(dy) > 64:
                    raise SessionError("manual node adjustment exceeds 64 content pixels")
                if dx or dy:
                    changed += 1
                out_row.append(target)
            committed.append(out_row)
        if changed == 0:
            return 0

        grid = np.full((len(committed), columns, 2), np.nan, dtype=np.float64)
        for i, row in enumerate(committed):
            for j, node in enumerate(row):
                if node[0] is not None:
                    grid[i, j] = node
        try:
            coverage = float(calib.coverage_mask(grid, tuple(content_size)).mean())
        except (ValueError, TypeError, OverflowError):
            raise SessionError("manual warp coverage could not be validated") from None
        if not np.isfinite(coverage) or not 0 <= coverage <= 1:
            raise SessionError("manual warp coverage is invalid")
        # All validation is done: only now modify the in-memory project.
        new_result = dict(self.project.result)
        new_result["mesh"] = committed
        new_result["coverage"] = coverage
        new_result["manual_edit_nodes"] = new_result.get("manual_edit_nodes", 0) + changed
        self.project.result = new_result
        self.project.steps_done = [
            stage for stage in self.project.steps_done
            if stage not in ("Export", "RecoverExport")
        ]
        self.project.steps_done.append("Edit")
        self.dirty = True
        self._note(
            f"manual warp adjusted {changed} observed nodes; "
            "hardware optical acceptance NOT_VERIFIED")
        return changed

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

    def inspect_camera_profile(self, path):
        """Validate one selected camera profile with zero camera/network access.

        Never store source URIs, credentials or the private profile's path.
        """
        from .camera_sources import CameraSourceError, profile_status, read_profile

        if not path:
            raise SessionError("select an existing private camera profile")
        try:
            result = profile_status(read_profile(path))
        except (CameraSourceError, OSError, ValueError, TypeError):
            raise SessionError("private camera profile refused or unreadable") from None
        self._note(
            f"offline camera profile validated: {result['camera_type']}; "
            "camera_connection=NOT_TESTED; hardware_optical_acceptance=NOT_VERIFIED"
        )
        return result

    def inspect_rig(self, *, expected_projectors=2):
        """Read Windows display rectangles only, without projector operations."""
        from .rig_preflight import RigPreflightError, rig_preflight

        try:
            report = rig_preflight(expected_projectors=expected_projectors)
        except RigPreflightError as exc:
            raise SessionError(f"read-only rig inspection refused: {exc}") from None
        except (OSError, ValueError, TypeError):
            raise SessionError("read-only Windows rig inspection unavailable") from None
        self._note(
            f"read-only rig preflight: {report['display_layout_gate']}; "
            "projector_identity=NOT_VERIFIED; hardware_optical_acceptance=NOT_VERIFIED"
        )
        return report

    def compare_projector_seam(self, other_path):
        """Read-only two-projector geometry check using the current in-memory project.

        No saved project state, capture frame, camera, or display is modified.
        Failed geometry is reported as an explicit software gate, not success.
        """
        from .two_projector_check import TwoProjectorError, check_two_projectors

        if not other_path:
            raise SessionError("select another calibrated projector project")
        other = Path(other_path)
        if self.path is not None and self.path.resolve() == other.resolve():
            raise SessionError("choose a different second-projector file")
        try:
            candidate = Project.load(other)
            report = check_two_projectors([self.project, candidate])
        except (TwoProjectorError, ValueError, TypeError, KeyError, OSError) as exc:
            raise SessionError(f"two-projector check refused: {exc}") from exc
        self._note(
            f"two-projector software geometry: {report['software_seam_gate']}; "
            "hardware_optical_acceptance=NOT_VERIFIED"
        )
        return report

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
