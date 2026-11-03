import numpy as np
import pytest

from vclone import render

IMG = np.full((40, 60, 3), 128, np.uint8)
MESH = np.array([[[0, 0], [59, 0]], [[0, 39], [59, 39]]], float)


def test_good_render_unchanged():
    out = render.render_projector(IMG, MESH, (30, 20))
    assert out.shape == (20, 30, 3) and out[10, 15].tolist() == [128, 128, 128]


@pytest.mark.parametrize("size", [(0, 20), (30, 0), (-3, 20), (30.5, 20), (30,), None, "ab", (True, 20),
                                  (10 ** 7, 10 ** 7), (20000, 10)])
def test_bad_proj_size_fails_closed(size):
    with pytest.raises(ValueError, match="proj_size"):
        render.render_projector(IMG, MESH, size)


@pytest.mark.parametrize("content", [None, np.zeros(5, np.uint8), np.zeros((0, 5, 3), np.uint8),
                                     np.zeros((5, 0), np.uint8), np.zeros((4, 4, 3, 2), np.uint8), "img"])
def test_bad_content_fails_closed(content):
    with pytest.raises(ValueError, match="content"):
        render.render_projector(content, MESH, (30, 20))


def test_grayscale_and_float_content_still_work():
    assert render.render_projector(np.full((40, 60), 7, np.uint8), MESH, (30, 20)).shape == (20, 30)
    assert render.render_projector(IMG.astype(np.float32), MESH, (30, 20)).dtype == np.float32


def test_infinite_mesh_node_is_treated_as_unobserved_not_garbage():
    mesh = MESH.copy()
    mesh[1, 1] = (np.inf, 39.0)
    out = render.render_projector(IMG, mesh, (30, 20))
    assert out.shape == (20, 30, 3) and (out[-1, -1] == 0).all()


def test_all_nonfinite_mesh_gives_black_frame():
    mesh = np.full((2, 2, 2), np.inf)
    assert not render.render_projector(IMG, mesh, (30, 20)).any()


@pytest.mark.parametrize("alpha", [np.full((40, 60), np.nan), np.full((40, 60), 2.0),
                                   np.full((40, 60), -0.5), np.full((40, 60), np.inf)])
def test_alpha_must_be_finite_and_within_unit_range(alpha):
    with pytest.raises(ValueError, match="alpha"):
        render.render_projector(IMG, MESH, (30, 20), alpha=alpha)


def test_valid_alpha_still_scales_output():
    out = render.render_projector(IMG, MESH, (30, 20), alpha=np.full((40, 60), 0.5))
    assert abs(int(out[10, 15, 0]) - 64) <= 1
