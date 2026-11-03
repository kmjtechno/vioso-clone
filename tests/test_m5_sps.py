import datetime
import pytest

from vclone import sps
from vclone.project import Project


def _proj():
    return Project(name="p", content_space="c", displays=[{"id": 1}], scan={"a": [1, 2]},
                   result={"mesh": [[[1.0, 2.0], None]]})


@pytest.mark.parametrize("compress", [True, False])
def test_roundtrip(tmp_path, compress):
    f = tmp_path / "a.sps"
    sps.save(_proj(), f, compress)
    assert sps.load(f) == _proj()
    assert f.read_bytes().startswith(b"<?xml") and b"<VIOSO>" in f.read_bytes()


def test_rejects_garbage_and_truncation():
    with pytest.raises(ValueError):
        sps.loads(b"nope")
    with pytest.raises(ValueError):
        sps.loads(sps.dumps(_proj())[:-5])


def test_default_filename():
    n = datetime.datetime(2026, 11, 3, 4, 5, 6, 7000)
    assert sps.default_filename(n) == "SPSet_XML_261103_040506_007.sps"


def test_cmdline_sps_persists(tmp_path):
    from vclone.cmdline import parse
    from vclone.project import run_cmdline
    f = tmp_path / "x.sps"
    assert run_cmdline(parse(["/Q:Design", f"/L:{f}"])) == 3  # missing input
    assert f.exists() is False  # failed step must not write a file
    f2 = tmp_path / "y.sps"
    sps.save(Project(content_space="c", displays=[{"id": 1}]), f2)
    assert run_cmdline(parse(["/Q:Design", f"/L:{f2}"])) == 0
    assert sps.load(f2).steps_done == ["Design"]
