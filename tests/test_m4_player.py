import pytest

from vclone.player import Playlist, PlaylistError, Player, UnsupportedSource


def mk(tmp_path, names):
    for n in names:
        (tmp_path / n).write_bytes(b"x")
    return [str(tmp_path / n) for n in names]


def test_playlist_order_and_loop(tmp_path):
    a, b = mk(tmp_path, ["a.png", "b.png"])
    pl = Playlist()
    pl.add(a, 1.0)
    pl.add(b, 2.0)
    assert [i.path for i in pl.items] == [a, b]
    p = Player(pl, loop=True)
    assert p.current.path == a
    assert p.next().path == b
    assert p.next().path == a  # wraps
    assert p.prev().path == b


def test_no_loop_stops_at_end(tmp_path):
    (a,) = mk(tmp_path, ["a.png"])
    pl = Playlist()
    pl.add(a, 1.0)
    p = Player(pl, loop=False)
    assert p.next() is None
    assert p.finished


def test_tick_advances_by_duration(tmp_path):
    a, b = mk(tmp_path, ["a.png", "b.png"])
    pl = Playlist()
    pl.add(a, 1.0)
    pl.add(b, 2.0)
    p = Player(pl, loop=False)
    p.tick(0.5)
    assert p.current.path == a
    p.tick(0.6)
    assert p.current.path == b
    p.tick(5)
    assert p.finished


def test_save_load_roundtrip(tmp_path):
    (a,) = mk(tmp_path, ["a.png"])
    pl = Playlist()
    pl.add(a, 3.5)
    f = tmp_path / "pl.json"
    pl.save(f)
    assert Playlist.load(f).items[0].duration == 3.5


def test_validation(tmp_path):
    pl = Playlist()
    with pytest.raises(PlaylistError):
        pl.add(str(tmp_path / "missing.png"), 1.0)
    (a,) = mk(tmp_path, ["a.png"])
    with pytest.raises(PlaylistError):
        pl.add(a, 0)
    with pytest.raises(PlaylistError):
        Player(Playlist())
    (tmp_path / "bad.json").write_text("{nope")
    with pytest.raises(PlaylistError):
        Playlist.load(tmp_path / "bad.json")


def test_ndi_is_unsupported(tmp_path):
    with pytest.raises(UnsupportedSource):
        Playlist().add("ndi://CAM1", 1.0)
