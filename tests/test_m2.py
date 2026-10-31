import cv2
import numpy as np
import pytest

from vclone import calib, cmdline, project

PW, PH = 64, 48
CW, CH = 320, 240
# projector -> camera homography (about 4 camera px per projector px, mild perspective)
HPC = np.array([[4.0, 0.3, 20.0], [0.2, 3.8, 15.0], [0.0004, 0.0002, 1.0]])


def shoot(pat, dark=10, bright=200):
    """Synthetic camera: warp the projected pattern; outside the projector footprint the camera sees 0."""
    img = cv2.warpPerspective(pat, HPC, (CW, CH), flags=cv2.INTER_NEAREST, borderValue=0)
    foot = cv2.warpPerspective(np.full_like(pat, 255), HPC, (CW, CH), flags=cv2.INTER_NEAREST) > 0
    return np.where(foot, np.where(img > 127, bright, dark), 0).astype(np.uint8)


def capture_set():
    pats, invs = calib.graycode_patterns(PW, PH)
    return [shoot(p) for p in pats], [shoot(i) for i in invs]


def test_graycode_decode_matches_geometry():
    pos, neg = capture_set()
    dec = calib.decode_graycode(pos, neg, (PW, PH))
    assert dec.valid.sum() > 0.3 * CW * CH
    ys, xs = np.nonzero(dec.valid)
    pts = np.stack([xs, ys], 1).astype(np.float64).reshape(-1, 1, 2)
    inv = cv2.perspectiveTransform(pts, np.linalg.inv(HPC)).reshape(-1, 2)
    assert np.abs(dec.px[ys, xs] - inv[:, 0]).max() <= 1.5
    assert np.abs(dec.py[ys, xs] - inv[:, 1]).max() <= 1.5


def test_decode_rejects_wrong_count():
    pos, neg = capture_set()
    with pytest.raises(ValueError):
        calib.decode_graycode(pos[:-1], neg[:-1], (PW, PH))


def test_unlit_region_is_invalid():
    pos, neg = capture_set()
    dec = calib.decode_graycode(pos, neg, (PW, PH))
    assert not dec.valid[0, 0] and not dec.valid[CH - 1, CW - 1]


def test_mesh_matches_ground_truth_including_borders():
    pos, neg = capture_set()
    dec = calib.decode_graycode(pos, neg, (PW, PH))
    mesh = calib.proj_to_cam_mesh(dec, (PW, PH), nodes=(5, 4), radius=4)
    assert not np.isnan(mesh).any()
    gx = np.linspace(0, PW - 1, 5)
    gy = np.linspace(0, PH - 1, 4)
    truth = np.array([[[x, y] for x in gx] for y in gy], np.float64)
    exp = cv2.perspectiveTransform(truth.reshape(-1, 1, 2), HPC).reshape(truth.shape)
    assert np.abs(mesh - exp).max() < 3.0


def test_homography_and_warp_mesh_nan_preserved():
    cam = [(0, 0), (100, 0), (100, 50), (0, 50)]
    content = [(0, 0), (1000, 0), (1000, 500), (0, 500)]
    H = calib.cam_to_content_homography(cam, content)
    m = np.array([[[50.0, 25.0], [np.nan, np.nan]]])
    out = calib.warp_mesh(m, H)
    assert np.allclose(out[0, 0], [500, 250]) and np.isnan(out[0, 1]).all()
    with pytest.raises(ValueError):
        calib.cam_to_content_homography([(0, 0)] * 4, content)


def test_edge_blend_overlap_sums_to_one():
    a = np.zeros((20, 100), bool)
    a[:, :60] = True
    b = np.zeros((20, 100), bool)
    b[:, 40:] = True
    alphas, lin = calib.edge_blend_weights([a, b])
    total = lin[0] + lin[1]
    assert np.allclose(total[a | b], 1.0, atol=1e-5)
    assert lin[0][10, 5] == pytest.approx(1.0) and lin[1][10, 95] == pytest.approx(1.0)
    assert lin[0][10, 45] > lin[0][10, 55]
    assert (alphas[0] >= lin[0] - 1e-6).all()


def test_pipeline_calibrate_export_via_cmdline(tmp_path):
    pos, neg = capture_set()
    for i, (p, n) in enumerate(zip(pos, neg)):
        cv2.imwrite(str(tmp_path / f"p{i:02d}.png"), p)
        cv2.imwrite(str(tmp_path / f"n{i:02d}.png"), n)
    corners_proj = np.array([[0, 0], [PW - 1, 0], [PW - 1, PH - 1], [0, PH - 1]], np.float64)
    cam_c = cv2.perspectiveTransform(corners_proj.reshape(-1, 1, 2), HPC).reshape(-1, 2)
    proj = project.Project("syn", scan={
        "dir": str(tmp_path), "proj_size": [PW, PH], "content_size": [640, 480], "nodes": [5, 4],
        "cam_corners": cam_c.tolist(), "content_corners": [[0, 0], [639, 0], [639, 479], [0, 479]],
    })
    f = tmp_path / "proj.json"
    proj.save(f)
    assert project.run_cmdline(cmdline.parse([f"/L:{f}", '/Q:"Calibrate"'])) == 0
    done = project.Project.load(f)
    assert done.steps_done == ["Calibrate"] and done.result["coverage"] > 0.9
    assert project.run_cmdline(cmdline.parse([f"/L:{f}", '/Q:"Export"'])) == 0
    assert (tmp_path / "warp.json").exists()
    m = np.array(done.result["mesh"], dtype=float)
    assert np.abs(m[0, 0] - [0, 0]).max() < 12 and np.abs(m[-1, -1] - [639, 479]).max() < 12


def test_calibrate_without_captures_is_missing_input(tmp_path):
    p = project.Project("x", scan={"dir": str(tmp_path), "proj_size": [PW, PH], "content_size": [10, 10],
                                  "cam_corners": [[0, 0]] * 4, "content_corners": [[0, 0]] * 4})
    with pytest.raises(project.MissingInput):
        project.run_step(p, "Calibrate")
