import socket
import urllib.error
import urllib.request

import pytest

from vclone.project import Project
from vclone.remote import RemoteController, RemoteServer


def test_controller_commands(tmp_path):
    c = RemoteController(Project("p"), base_dir=tmp_path)
    assert c.handle("PING") == "OK pong"
    assert c.handle("status").startswith("OK ") and "p" in c.handle("STATUS")
    assert c.handle(f"SAVE out.json") == "OK saved"
    assert (tmp_path / "out.json").is_file()
    assert c.handle("LOAD out.json") == "OK loaded"
    assert c.handle("LOAD nope.json").startswith("ERR")
    assert c.handle("STEP Bogus").startswith("ERR")
    assert c.handle("STEP Calibrate").startswith("ERR")  # no scan data: never fake success
    assert c.handle("STEP").startswith("ERR")
    assert c.handle("FLY").startswith("ERR unknown command")
    assert c.handle("") .startswith("ERR")


def test_save_load_cannot_escape_base_dir(tmp_path):
    c = RemoteController(Project("p"), base_dir=tmp_path / "w")
    (tmp_path / "w").mkdir()
    assert c.handle("SAVE ../evil.json").startswith("ERR")
    assert not (tmp_path / "evil.json").exists()
    assert c.handle("LOAD ../x.json").startswith("ERR")


@pytest.fixture
def server(tmp_path):
    s = RemoteServer(RemoteController(Project("srv"), base_dir=tmp_path), host="127.0.0.1")
    s.start()
    yield s
    s.stop()


def test_tcp_line_protocol(server):
    with socket.create_connection(("127.0.0.1", server.tcp_port), timeout=3) as sk:
        f = sk.makefile("rw", newline="\n")
        f.write("PING\nSTATUS\n"); f.flush()
        assert f.readline().strip() == "OK pong"
        assert "srv" in f.readline()


def test_udp_datagram(server):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
        sk.settimeout(3)
        sk.sendto(b"PING", ("127.0.0.1", server.udp_port))
        assert sk.recvfrom(1024)[0].decode().strip() == "OK pong"


def test_http_control(server):
    base = f"http://127.0.0.1:{server.http_port}"
    body = urllib.request.urlopen(base + "/control.htm?cmd=PING", timeout=3).read().decode()
    assert body.strip() == "OK pong"
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base + "/control.htm?cmd=FLY", timeout=3)
    assert e.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(base + "/other", timeout=3)
    assert e.value.code == 404


def test_binds_loopback_by_default():
    s = RemoteServer(RemoteController(Project("x")))
    assert s.host == "127.0.0.1"
