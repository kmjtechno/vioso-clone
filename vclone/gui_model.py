"""Qt-free session model behind the GUI: project load/save, step runner, log. Fully unit-testable."""
from pathlib import Path
import json

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
