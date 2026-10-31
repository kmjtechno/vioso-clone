"""Project model and /Q step dispatch. Calibrate/Recalibrate/Export run the M2 engine; the rest are stubs."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import calib
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
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Project":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        cam = d.get("camera")
        return cls(d.get("name", "untitled"), CameraIntrinsics(**cam) if cam else None,
                   d.get("content_space", ""), d.get("displays", []), d.get("steps_done", []),
                   d.get("scan", {}), d.get("result", {}))


class NotImplementedStep(NotImplementedError):
    pass


class MissingInput(RuntimeError):
    pass


def _calibrate(project: Project) -> None:
    sc = project.scan
    need = ("dir", "proj_size", "cam_corners", "content_corners", "content_size")
    miss = [k for k in need if k not in sc]
    if miss:
        raise MissingInput(f"project.scan missing: {', '.join(miss)}")
    w, h = sc["proj_size"]
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


def _export(project: Project) -> None:
    if not project.result:
        raise MissingInput("nothing to export: run Calibrate first")
    out = Path(project.scan.get("out") or Path(project.scan.get("dir", ".")) / "warp.json")
    out.write_text(json.dumps({"name": project.name, **project.result}), encoding="utf-8")


_IMPL = {"Calibrate": _calibrate, "Recalibrate": _calibrate, "Export": _export}


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

    Exit codes: 0 ok, 2 step not implemented, 3 missing input.
    """
    step = cl.values.get("step")
    if not step:
        return 0
    sps = cl.values.get("sps")
    is_json = bool(sps) and Path(sps).suffix == ".json"
    proj = Project.load(sps) if is_json and Path(sps).exists() else Project()
    try:
        run_step(proj, step)
    except NotImplementedStep as e:
        print(e)
        return 2
    except MissingInput as e:
        print(e)
        return 3
    if is_json:
        proj.save(sps)
    return 0
