import cv2
import numpy as np
import pytest

from vclone.project import MissingInput, Project, render_preview


def _proj(w, h, nx=5, ny=4):
    xs, ys = np.meshgrid(np.linspace(0, w - 1, nx), np.linspace(0, h - 1, ny))
    p = Project("p")
    p.scan = {"proj_size": [w, h]}
    p.result = {"mesh": np.stack([xs, ys], -1).tolist()}
    return p


def test_preview_renders_calibrated_mesh(tmp_path):
    img = np.random.default_rng(1).integers(0, 255, (40, 60, 3), dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "c.png"), img)
    render_preview(_proj(60, 40), tmp_path / "c.png", tmp_path / "o.png")
    out = cv2.imread(str(tmp_path / "o.png"))
    assert out.shape == img.shape and np.abs(out.astype(int) - img).max() <= 1


def test_preview_treats_null_nodes_as_unobserved(tmp_path):
    cv2.imwrite(str(tmp_path / "c.png"), np.full((40, 60, 3), 255, np.uint8))
    p = _proj(60, 40)
    p.result["mesh"][0] = [None] * 5
    p.result["mesh"][1] = [[None, None]] * 5
    render_preview(p, tmp_path / "c.png", tmp_path / "o.png")
    assert cv2.imread(str(tmp_path / "o.png"))[:5].max() == 0


def test_preview_needs_calibration_and_content(tmp_path):
    with pytest.raises(MissingInput):
        render_preview(Project("p"), tmp_path / "c.png", tmp_path / "o.png")
    with pytest.raises(MissingInput):
        render_preview(_proj(60, 40), tmp_path / "missing.png", tmp_path / "o.png")


def test_cli_preview_subcommand(tmp_path):
    import cv2
    from vclone.__main__ import main
    p = _proj(60, 40)
    pf = tmp_path / "p.json"
    p.save(pf)
    cv2.imwrite(str(tmp_path / "c.png"), np.full((40, 60, 3), 90, np.uint8))
    out = tmp_path / "o.png"
    assert main(["preview", str(pf), str(tmp_path / "c.png"), str(out)]) == 0
    assert out.is_file()
    assert main(["preview", str(pf), str(tmp_path / "missing.png"), str(out)]) == 2
