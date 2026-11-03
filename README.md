# VIOSO-Clone (`vclone`)

Clean-room reimplementation effort for a VIOSO 7 style projector-calibration tool.
Python, numpy/OpenCV. No original code or assets are copied; licensing mechanisms
(Soraco QLM etc.) are deliberately **not** implemented.

## Status (honest)

Working and tested on **synthetic data only**. Nothing here is hardware evidence and no
claim of compatibility with the original `.sps` format is made (see `SPEC.md` §3.6 and
`docs/re_notes_sps.md`: the `.sps` internals are not established).

| Area | State |
|---|---|
| Gray-code pattern generation, decode, projector→camera mesh | implemented (`vclone/calib.py`) |
| Homography to content space, multi-plane RANSAC, intrinsics with quality gates | implemented, fail-closed gates |
| Warp mesh, coverage mask, edge-blend weights | implemented |
| CPU software renderer (warp + blend) | implemented (`vclone/render.py`) |
| `/L /Q ...` command line steps (Calibrate, Recalibrate, Export, Design, Edit, Edit MRD, Configure) | implemented (`vclone/project.py`); Activate/Deactivate refuse on purpose |
| Playlist player, remote control, task-script runner | implemented at software level (`player.py`, `remote.py`, `script.py`) |
| Qt GUI | minimal window (`gui.py`); not a full mirror of the original UI |
| DirectX/OpenGL output | **not implemented** (raises `UnsupportedOutput`) |
| Original `.sps` read/write | **not implemented** (internals unknown) |
| Real camera/projector capture hardware | **not implemented** |

"Full parity" with the original product is a multi-month effort; this repo is a verified
foundation, not a finished replacement.

## Run

```
pip install numpy opencv-python pytest   # PySide6 only for the GUI
python -m pytest -q                      # tests (a few skip when VIOSO 7 is not installed)
python examples/synthetic_demo.py        # simulated capture -> Calibrate -> Export -> preview.png
python -m vclone /L:project.json '/Q:"Calibrate"'
```

The demo prints the output directory; open `preview.png` there to see the warped test grid.
The CLI project format is the clone's own JSON (`Project` in `vclone/project.py`) plus an
experimental fail-closed XML dialect (`vclone/projectxml.py`).

## Layout

- `vclone/` source, `tests/` pytest suite, `SPEC.md` observed formats and milestones,
  `docs/re_notes_sps.md` read-only static-analysis notes (verified vs. inferred marked).
