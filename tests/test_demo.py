import runpy
from pathlib import Path

import cv2
import numpy as np

DEMO = Path(__file__).resolve().parent.parent / "examples" / "synthetic_demo.py"


def test_synthetic_demo_runs_end_to_end(tmp_path):
    ns = runpy.run_path(str(DEMO))
    result = ns["run"](tmp_path)
    assert result["calibrate_exit"] == 0 and result["export_exit"] == 0
    assert result["coverage"] > 0.9
    assert (tmp_path / "warp.json").exists()
    frame = cv2.imread(str(tmp_path / "preview.png"))
    assert frame is not None and frame.shape == (48, 64, 3) and frame.any()
    assert np.isfinite(result["corner_error_px"]) and result["corner_error_px"] < 12
