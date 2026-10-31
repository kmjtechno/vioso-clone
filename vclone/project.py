"""Project model and /Q step dispatch. Steps are stubs until M2 (calibration engine)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

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

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path) -> "Project":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        cam = d.get("camera")
        return cls(d.get("name", "untitled"), CameraIntrinsics(**cam) if cam else None,
                   d.get("content_space", ""), d.get("displays", []), d.get("steps_done", []))


class NotImplementedStep(NotImplementedError):
    pass


def run_step(project: Project, step: str) -> Project:
    """Dispatch a /Q step. Every step is a stub in M1 and raises NotImplementedStep."""
    if step not in STEPS:
        raise ValueError(f"unknown step: {step!r}")
    raise NotImplementedStep(f"step {step!r} is not implemented yet (planned for M2+)")


def run_cmdline(cl: CmdLine) -> int:
    """Load the project named by /L (if any) and run the /Q step. Returns a process exit code."""
    step = cl.values.get("step")
    if not step:
        return 0
    sps = cl.values.get("sps")
    proj = Project.load(sps) if sps and Path(sps).suffix == ".json" and Path(sps).exists() else Project()
    try:
        run_step(proj, step)
    except NotImplementedStep as e:
        print(e)
        return 2
    return 0
