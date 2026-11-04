"""Project model and /Q step dispatch. every step except the licensing ones is implemented."""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import calib, render
from . import sps as sps_io
from .cmdline import STEPS, CmdLine
from .configs import CameraIntrinsics


@dataclass
class Project:
    """Clone's own project format (JSON). The original .sps format is not reverse-engineered yet."""
    name: str = "untitled"
    camera: CameraIntrinsics | None = None
    content_space: str = ""
    displays: list[dict] = field(default_factory=list)
    steps_done: list[str] = field(default_factory=list)
    # scan: dir, proj_size, content_size, cam_corners, content_corners, optional nodes/out
    scan: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)  # mesh (content space, null = unobserved), coverage

    def save(self, path) -> None:
        """Atomic same-directory JSON save: never truncate an existing owner file."""
        target = Path(path)
        if (target.is_symlink() or (target.exists() and not target.is_file())
                or not target.parent.is_dir() or target.parent.is_symlink()):
            raise ValueError("project target must be a regular path in an existing directory")
        # Serialise first, before opening files: an invalid project must leave files untouched.
        payload = (json.dumps(asdict(self), indent=2, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > 32 * 1024 * 1024:
            raise ValueError("project JSON exceeds 32 MiB limit")
        fd, pending = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".pending",
                                       dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Re-check under the same-directory atomic replace; never follow target symlinks.
            if target.is_symlink() or (target.exists() and not target.is_file()):
                raise ValueError("project target changed during save")
            os.replace(pending, target)
        finally:
            if os.path.exists(pending):
                os.unlink(pending)

    @classmethod
    def load(cls, path) -> "Project":
        """Load clone JSON only; reject symlinks, oversized or nonstandard JSON."""
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise ValueError("project source must be a regular non-symlink file")
        if not 0 < source.stat().st_size <= 32 * 1024 * 1024:
            raise ValueError("project JSON must be 1..32 MiB")

        def reject_constant(value):
            raise ValueError(f"invalid non-finite JSON constant: {value}")

        d = json.loads(source.read_text(encoding="utf-8"), parse_constant=reject_constant)
        if not isinstance(d, dict):
            raise ValueError("project JSON root must be an object")
        if (not isinstance(d.get("name", "untitled"), str)
                or not isinstance(d.get("scan", {}), dict)
                or not isinstance(d.get("result", {}), dict)
                or not isinstance(d.get("steps_done", []), list)
                or not isinstance(d.get("displays", []), list)):
            raise ValueError("project JSON has invalid top-level field types")
        cam = d.get("camera")
        if cam is not None and not isinstance(cam, dict):
            raise ValueError("project camera must be an object or null")
        return cls(d.get("name", "untitled"), CameraIntrinsics(**cam) if cam else None,
                   d.get("content_space", ""), d.get("displays", []), d.get("steps_done", []),
                   d.get("scan", {}), d.get("result", {}))


class NotImplementedStep(NotImplementedError):
    pass


class MissingInput(RuntimeError):
    pass


class InvalidInput(ValueError):
    pass


def _calibrate(project: Project) -> None:
    sc = project.scan
    need = ("dir", "proj_size", "cam_corners", "content_corners", "content_size")
    miss = [k for k in need if k not in sc]
    if miss:
        raise MissingInput(f"project.scan missing: {', '.join(miss)}")
    try:
        w, h = sc["proj_size"]
        if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in (w, h)):
            raise ValueError(f"proj_size must be two positive integers: {sc['proj_size']!r}")
        n = len(calib.graycode_patterns(w, h)[0])
        d = Path(sc["dir"])
        load = lambda name: cv2.imread(str(d / name), cv2.IMREAD_GRAYSCALE)
        pos = [load(f"p{i:02d}.png") for i in range(n)]
        neg = [load(f"n{i:02d}.png") for i in range(n)]
        if any(im is None for im in pos + neg):
            raise MissingInput(f"expected {2 * n} capture files p00.png/n00.png... in {d}")
        dec = calib.decode_graycode(pos, neg, (w, h))
        cam_mesh = calib.proj_to_cam_mesh(dec, (w, h), tuple(sc.get("nodes", (17, 9))))
        H = calib.cam_to_content_homography(sc["cam_corners"], sc["content_corners"])
        mesh = calib.warp_mesh(cam_mesh, H)
        cov = calib.coverage_mask(mesh, tuple(sc["content_size"]))
        project.result = {"mesh": np.where(np.isnan(mesh), None, mesh).tolist(),
                          "coverage": float(cov.mean())}
    except (ValueError, TypeError, OverflowError) as e:
        raise InvalidInput(f"invalid scan configuration: {e}") from e


def _export(project: Project) -> None:
    if not project.result:
        raise MissingInput("nothing to export: run Calibrate first")
    out = Path(project.scan.get("out") or Path(project.scan.get("dir", ".")) / "warp.json")
    out.write_text(json.dumps({"name": project.name, **project.result}), encoding="utf-8")


def render_frame(project: Project, content_path) -> np.ndarray:
    """Return a CPU-calibrated projector frame without creating temporary files."""
    if not project.result.get("mesh") or "proj_size" not in project.scan:
        raise MissingInput("nothing to render: run Calibrate first")
    img = cv2.imread(str(content_path), cv2.IMREAD_COLOR)
    if img is None:
        raise MissingInput(f"cannot read content image: {content_path}")
    nan2 = [float("nan")] * 2
    mesh = np.array([[nan2 if n is None else [float("nan") if v is None else v for v in n] for n in row]
                     for row in project.result["mesh"]], dtype=np.float64)
    w, h = project.scan["proj_size"]
    return render.render_projector(img, mesh, (w, h))


def render_preview(project: Project, content_path, out_path) -> None:
    """Write a CPU-calibrated projector frame to a PNG; does not show a window."""
    frame = render_frame(project, content_path)
    if not cv2.imwrite(str(out_path), frame):
        raise MissingInput(f"cannot write preview: {out_path}")


def _design(project: Project) -> None:
    if not project.content_space or not project.displays:
        raise MissingInput("Design needs content_space and at least one display")
    project.result["design"] = {"content_space": project.content_space, "displays": len(project.displays)}


def _edit(project: Project) -> None:
    mesh = project.result.get("mesh")
    if not mesh:
        raise MissingInput("nothing to edit: run Calibrate first")
    new = [[None if n is None or n[0] is None else list(n) for n in row] for row in mesh]
    edits = project.scan.get("edits", [])
    for e in edits:
        try:
            j, i = e["node"]
            if any(isinstance(v, bool) or not isinstance(v, (int, np.integer)) for v in (j, i)):
                raise TypeError("node indices must be integers")
            if any(isinstance(e[k], bool) for k in ("dx", "dy")):
                raise TypeError("dx/dy must be numbers")
            dx, dy = float(e["dx"]), float(e["dy"])
            if not (np.isfinite(dx) and np.isfinite(dy)):
                raise ValueError("dx/dy must be finite")
            if j < 0 or i < 0 or new[j][i] is None or new[j][i][0] is None:
                raise IndexError
        except (KeyError, TypeError, ValueError, IndexError):
            raise InvalidInput(f"bad edit (missing keys, out of range or unobserved node): {e!r}") from None
        new[j][i] = [new[j][i][0] + dx, new[j][i][1] + dy]
    project.result["mesh"] = new
    project.result["edits_applied"] = project.result.get("edits_applied", 0) + len(edits)


def _edit_mrd(project: Project) -> None:
    """Clone's own interpretation: blend-region tuning (gamma of the edge-blend ramp)."""
    if not project.result.get("mesh"):
        raise MissingInput("nothing to edit: run Calibrate first")
    g = project.scan.get("blend_gamma", 2.2)
    if isinstance(g, bool) or not isinstance(g, (int, float)) or not 0.5 <= g <= 4.0:
        raise InvalidInput(f"blend_gamma must be within 0.5..4.0, got {g!r}")
    project.result["blend_gamma"] = float(g)


def _configure(project: Project) -> None:
    cfg = project.scan.get("configure", {})
    types = {"dir": str, "out": str, "nodes": list, "proj_size": list, "content_size": list}
    for k, v in cfg.items():
        if k not in types or not isinstance(v, types[k]):
            raise InvalidInput(f"cannot configure {k!r}={v!r}")
    project.scan.update(cfg)


def _licensing(project: Project) -> None:
    raise NotImplementedStep("licensing steps are deliberately unsupported: the clone has no licence mechanism")


_IMPL = {"Calibrate": _calibrate, "Recalibrate": _calibrate, "Export": _export, "Design": _design,
         "Edit": _edit, "Edit MRD": _edit_mrd, "Configure": _configure, "RecoverExport": _export,
         "Activate": _licensing, "Deactivate": _licensing}


def run_step(project: Project, step: str) -> Project:
    """Dispatch a /Q step. Calibrate/Recalibrate/Export are real; the others raise NotImplementedStep."""
    if step not in STEPS:
        raise ValueError(f"unknown step: {step!r}")
    fn = _IMPL.get(step)
    if fn is None:
        raise NotImplementedStep(f"step {step!r} is not implemented yet (planned for M3+)")
    fn(project)
    project.steps_done.append(step)
    return project


def run_cmdline(cl: CmdLine) -> int:
    """Load the project named by /L (if any) and run the /Q step.

    Exit codes: 0 ok, 2 step not implemented, 3 missing input, 4 invalid input.
    """
    step = cl.values.get("step")
    if not step:
        return 0
    sps = cl.values.get("sps")
    suffix = Path(sps).suffix.lower() if sps else ""
    is_json, is_sps = suffix == ".json", suffix == ".sps"
    persist = is_json or is_sps
    if persist and Path(sps).exists():
        proj = Project.load(sps) if is_json else sps_io.load(sps)
    else:
        proj = Project()
    try:
        run_step(proj, step)
    except NotImplementedStep as e:
        print(e)
        return 2
    except MissingInput as e:
        print(e)
        return 3
    except InvalidInput as e:
        print(e)
        return 4
    if is_json:
        proj.save(sps)
    elif is_sps:
        sps_io.save(proj, sps)
    return 0
