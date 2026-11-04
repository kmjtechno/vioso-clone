"""Fail-closed regression cases for untrusted clone-format .sps containers.

No native VIOSO interoperability is claimed by these synthetic fixtures.
"""
import re
import zlib

import pytest

from vclone import sps
from vclone.project import Project


def _proj():
    return Project(name="bounded", content_space="screen", displays=[{"id": 1}])


def _replace_attr(container, name, value):
    offset = int(re.search(rb'binOffset="([0-9]{20})"', container).group(1))
    header, payload = container[:offset], container[offset:]
    pattern = rb'\b' + name.encode("ascii") + rb'="[^"]*"'
    header, count = re.subn(pattern, name.encode() + b'="' + value.encode() + b'"', header, count=1)
    assert count == 1
    if name != "binOffset":
        header = re.sub(rb'binOffset="[0-9]{20}"',
                        f'binOffset="{len(header):020d}"'.encode(), header)
    return header + payload


@pytest.mark.parametrize(("name", "value"), [
    ("binOffset", "-0000000000000000001"),
    ("binSize", "-1"),
    ("binSize", "999999999999999999999"),
    ("binSizeRaw", "999999999999999999999"),
    ("bCompressed", "yes"),
])
def test_reject_invalid_metadata(name, value):
    with pytest.raises(ValueError):
        sps.loads(_replace_attr(sps.dumps(_proj()), name, value))


@pytest.mark.parametrize("compress", [True, False])
def test_reject_trailing_bytes_and_bad_xml(compress):
    payload = sps.dumps(_proj(), compress=compress)
    with pytest.raises(ValueError, match="trailing"):
        sps.loads(payload + b"JUNK")
    with pytest.raises(ValueError, match="XML"):
        sps.loads(payload.replace(b"<File ", b"<F!le ", 1))


def test_reject_false_small_uncompressed_size_before_inflating():
    raw = b'{"name":"' + b"x" * 16384 + b'"}'
    blob = zlib.compress(raw)
    header = sps._header(0, len(blob), 32, True)
    header = sps._header(len(header), len(blob), 32, True)
    with pytest.raises(ValueError, match="mismatch"):
        sps.loads(header + blob)


def test_reject_compressed_stream_with_extra_bytes():
    raw = b'{"name":"ok"}'
    blob = zlib.compress(raw) + b"GARBAGE"
    header = sps._header(0, len(blob), len(raw), True)
    header = sps._header(len(header), len(blob), len(raw), True)
    with pytest.raises(ValueError, match="mismatch"):
        sps.loads(header + blob)


def test_reject_non_dict_json_and_invalid_compression_level():
    header = sps._header(0, 2, 2, False)
    header = sps._header(len(header), 2, 2, False)
    with pytest.raises(ValueError, match="JSON root"):
        sps.loads(header + b"[]")
    with pytest.raises(ValueError, match="compression level"):
        sps.dumps(_proj(), level=-1)


def test_bounded_disk_load_without_reading_oversized_file(tmp_path, monkeypatch):
    src = tmp_path / "too_large.sps"
    src.write_bytes(sps.dumps(_proj()))
    monkeypatch.setattr(sps, "MAX_CONTAINER_BYTES", src.stat().st_size - 1)
    with pytest.raises(ValueError, match="oversized"):
        sps.load(src)


def test_reject_unsupported_xml_encoding_as_invalid_container():
    source = sps.dumps(_proj())
    # Same-byte-length encoding name retains binOffset and isolates XML parser behavior.
    corrupted = source.replace(b'encoding="UTF-8"', b'encoding="UF8-8"', 1)
    with pytest.raises(ValueError, match="XML"):
        sps.loads(corrupted)
