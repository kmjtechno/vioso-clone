import numpy as np
import pytest

from vclone import render


def ident_mesh(w, h, nx=5, ny=4):
    xs, ys = np.meshgrid(np.linspace(0, w - 1, nx), np.linspace(0, h - 1, ny))
    return np.stack([xs, ys], -1)


def test_identity_mesh_reproduces_content():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, (40, 60, 3), dtype=np.uint8)
    out = render.render_projector(img, ident_mesh(60, 40), (60, 40))
    assert np.abs(out.astype(int) - img.astype(int)).max() <= 1


def test_scaled_mesh_samples_half_content():
    img = np.zeros((20, 40, 3), np.uint8)
    img[:, 25:] = 200
    mesh = ident_mesh(40, 20) * [0.5, 1.0]  # projector shows the left half only
    out = render.render_projector(img, mesh, (40, 20))
    assert out.max() == 0


def test_unobserved_nodes_render_black():
    img = np.full((40, 60, 3), 255, np.uint8)
    mesh = ident_mesh(60, 40)
    mesh[:2, :] = np.nan
    out = render.render_projector(img, mesh, (60, 40))
    assert out[:5].max() == 0 and out[-3:].min() == 255


def test_alpha_scales_output():
    img = np.full((40, 60, 3), 200, np.uint8)
    alpha = np.full((40, 60), 0.5, np.float32)
    out = render.render_projector(img, ident_mesh(60, 40), (60, 40), alpha=alpha)
    assert abs(int(out[20, 30, 0]) - 100) <= 1


def test_bad_inputs():
    with pytest.raises(ValueError):
        render.render_projector(np.zeros((4, 4, 3), np.uint8), np.zeros((3, 3)), (8, 8))
    with pytest.raises(ValueError):
        render.render_projector(np.zeros((4, 4, 3), np.uint8), ident_mesh(8, 8), (8, 8),
                                alpha=np.zeros((2, 2), np.float32))


def test_gpu_output_is_explicitly_unsupported():
    with pytest.raises(render.UnsupportedOutput):
        render.present("dx11", None)
