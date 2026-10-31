import math
from pathlib import Path

import numpy as np
import pytest

from vclone import cmdline, configs, intrinsics

DEPLOY = Path(r"C:\Program Files\VIOSO7\Deploy")
shipped = pytest.mark.skipif(not DEPLOY.exists(), reason="VIOSO install not present")


@shipped
def test_devices_shipped():
    cams = configs.load_devices(DEPLOY / "SPDevices.ini")
    assert cams and all(c.fx > 0 and c.width > 0 for c in cams)


@shipped
def test_other_shipped_files_parse():
    configs.load_surface_defs(DEPLOY / "SPSurDef.ini")
    configs.load_mp_presets(DEPLOY / "SPManualMPPreset.ini")
    assert configs.load_content_spaces(DEPLOY / "SPContentSpaces.ini")
    assert configs.load_calibrator_ini(DEPLOY / "Calibrator.ini")


def test_devices_roundtrip(tmp_path):
    cam = configs.CameraIntrinsics("x", 640, 480, 800.5, 801.5, 320.0, 240.0, -0.1, 0.05, 0.0, 0.001, -0.002)
    configs.save_devices(tmp_path / "d.ini", [cam])
    assert configs.load_devices(tmp_path / "d.ini") == [cam]


def test_surface_and_preset_parse(tmp_path):
    p = tmp_path / "s.ini"
    p.write_text(
        '<VIOSO><DesktopDisplay name="a" core="c" posX="-3840" posY="0" sizeX="3840" sizeY="2160" '
        'rows="1" cols="2" rotation="90"><Part iRow="0" iCol="1" name="S2"/></DesktopDisplay>'
        '<logicalDisplay name="L" idString="id" tProtocol="native"><topology rows="2" cols="3"/>'
        '<display iRow="0" iCol="0" idString="m" core="1.2.3.4"/></logicalDisplay>'
        '<MPPreset><Common tArrangement="grid"/><CalibSpace left="0" top="0" right="4096" bottom="2048"/>'
        '<Display name="B" core="c" left="0" top="0" right="1280" bottom="800" tUse="Keystone Rect"/>'
        '</MPPreset></VIOSO>')
    desk, logical = configs.load_surface_defs(p)
    assert desk[0].pos_x == -3840 and desk[0].parts[0].col == 1
    assert (logical[0].rows, logical[0].cols) == (2, 3) and logical[0].displays[0]["core"] == "1.2.3.4"
    pre = configs.load_mp_presets(p)[0]
    assert pre.calib_space == (0, 0, 4096, 2048) and pre.displays[0].use == "Keystone Rect"


def test_cmdline():
    cl = cmdline.parse(["/M", "/V", '/L:"a b.sps"', '/Q:"Calibrate;CloseAfter=yes"', "/Lang:1031", "/H"])
    assert {"minimized", "verbose"} <= cl.flags
    assert cl.values["sps"] == "a b.sps" and cl.values["step"] == "Calibrate"
    assert cl.close_after is True and cl.values["lang"] == 1031 and cl.values["script_host"] is True
    for bad in (["/Q:Bogus"], ["/Q:Export;CloseAfter=maybe"], ["/Zzz"], ["x"], ["/L"]):
        with pytest.raises(ValueError):
            cmdline.parse(bad)


def test_intrinsics_recovers_synthetic_camera():
    truth = configs.CameraIntrinsics("t", 1280, 960, 1500.0, 1510.0, 640.0, 480.0,
                                     -0.12, 0.08, 0.0, 0.0005, -0.0004)
    gx, gy = np.meshgrid(np.arange(9) * 30.0, np.arange(6) * 30.0)
    board = np.stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)], 1)
    rng = np.random.default_rng(1)
    objs, imgs = [], []
    for _ in range(12):
        r = rng.uniform(-0.4, 0.4, 3)
        t = np.array([-120, -75, 600]) + rng.uniform(-40, 40, 3)
        objs.append(board)
        imgs.append(intrinsics.project(truth, board, r, t))
    est, rms = intrinsics.calibrate_intrinsics(objs, imgs, (1280, 960))
    assert rms < 0.05
    assert abs(est.fx - truth.fx) / truth.fx < 0.01 and abs(est.cx - truth.cx) < 5


def test_project_roundtrip_and_step_stubs(tmp_path):
    from vclone import project
    cam = configs.CameraIntrinsics("c", 640, 480, 800.0, 800.0, 320.0, 240.0)
    p = project.Project("demo", cam, "cs", [{"name": "d"}], ["Design"])
    p.save(tmp_path / "p.json")
    assert project.Project.load(tmp_path / "p.json") == p
    for step in cmdline.STEPS - set(project._IMPL):
        with pytest.raises(project.NotImplementedStep):
            project.run_step(p, step)
    with pytest.raises(ValueError):
        project.run_step(p, "Bogus")
    assert project.run_cmdline(cmdline.parse(['/Q:"Design"'])) == 2
    assert project.run_cmdline(cmdline.parse(['/Q:"Export"'])) == 3
    assert project.run_cmdline(cmdline.parse(["/V"])) == 0
