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


def test_synthetic_demo_preserves_preexisting_output_files(tmp_path):
    ns = runpy.run_path(str(DEMO))
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / "p00.png"
    marker.write_bytes(b"owner capture - do not overwrite")
    import pytest
    with pytest.raises(FileExistsError):
        ns["run"](target)
    assert marker.read_bytes() == b"owner capture - do not overwrite"
    assert not (target / "warp.json").exists()


def test_synthetic_demo_refuses_symlink_target(tmp_path):
    import pytest
    ns = runpy.run_path(str(DEMO))
    real = tmp_path / "original"
    real.mkdir()
    alias = tmp_path / "linked"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable here")
    with pytest.raises(FileExistsError):
        ns["run"](alias)
    assert list(real.iterdir()) == []
