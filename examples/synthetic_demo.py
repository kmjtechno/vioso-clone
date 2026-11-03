"""End-to-end demo on SYNTHETIC data: fake camera captures -> Calibrate -> Export -> preview.

Run:  python examples/synthetic_demo.py [output_dir]

This exercises the clone's own pipeline with a simulated projector/camera pair. It is NOT
hardware evidence and says nothing about real VIOSO compatibility.
"""
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vclone import calib, cmdline, project  # noqa: E402

PW, PH, CW, CH = 64, 48, 320, 240
HPC = np.array([[4.0, 0.3, 20.0], [0.2, 3.8, 15.0], [0.0004, 0.0002, 1.0]])  # projector -> camera


def _shoot(pattern):
    img = cv2.warpPerspective(pattern, HPC, (CW, CH), flags=cv2.INTER_NEAREST, borderValue=0)
    foot = cv2.warpPerspective(np.full_like(pattern, 255), HPC, (CW, CH), flags=cv2.INTER_NEAREST) > 0
    return np.where(foot, np.where(img > 127, 200, 10), 0).astype(np.uint8)


def run(out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pats, invs = calib.graycode_patterns(PW, PH)
    for i, (p, n) in enumerate(zip(pats, invs)):
        cv2.imwrite(str(out / f"p{i:02d}.png"), _shoot(p))
        cv2.imwrite(str(out / f"n{i:02d}.png"), _shoot(n))
    corners = np.array([[0, 0], [PW - 1, 0], [PW - 1, PH - 1], [0, PH - 1]], np.float64)
    cam_c = cv2.perspectiveTransform(corners.reshape(-1, 1, 2), HPC).reshape(-1, 2)
    proj = project.Project("synthetic-demo", scan={
        "dir": str(out), "proj_size": [PW, PH], "content_size": [640, 480], "nodes": [9, 7],
        "cam_corners": cam_c.tolist(), "content_corners": [[0, 0], [639, 0], [639, 479], [0, 479]]})
    pfile = out / "project.json"
    proj.save(pfile)
    cal = project.run_cmdline(cmdline.parse([f"/L:{pfile}", '/Q:"Calibrate"']))
    exp = project.run_cmdline(cmdline.parse([f"/L:{pfile}", '/Q:"Export"']))
    done = project.Project.load(pfile)
    content = np.zeros((480, 640, 3), np.uint8)
    content[::40] = 255
    content[:, ::40] = 255
    cv2.imwrite(str(out / "content.png"), content)
    project.render_preview(done, out / "content.png", out / "preview.png")
    mesh = np.array(done.result["mesh"], dtype=float)
    err = float(max(np.abs(mesh[0, 0] - [0, 0]).max(), np.abs(mesh[-1, -1] - [639, 479]).max()))
    return {"calibrate_exit": cal, "export_exit": exp, "coverage": done.result["coverage"],
            "corner_error_px": err}


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="vclone_demo_")
    r = run(target)
    print(f"output: {target}")
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()})
    sys.exit(0 if r["calibrate_exit"] == 0 and r["export_exit"] == 0 else 1)
