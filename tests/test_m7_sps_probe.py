"""M7 metadata-only, fail-closed SPS inspection tests (synthetic fixtures)."""
import json
import subprocess
import sys

import pytest

from vclone import sps, sps_probe


def make_container(payload=b"{}", compressed=False):
    header = sps._header(0, len(payload), len(payload), compressed)
    return sps._header(len(header), len(payload), len(payload), compressed) + payload


@pytest.mark.parametrize("compressed", [True, False])
def test_inspect_synthetic_header_without_claiming_native_compatibility(tmp_path, compressed):
    data = make_container(compressed=compressed)
    path = tmp_path / "fake.sps"
    path.write_bytes(data)
    evidence = sps_probe.inspect_file(path)
    assert evidence.bin_offset + evidence.bin_size == len(data)
    assert evidence.file_version == "1.0.0"
    assert evidence.file_build == "1"
    assert evidence.compressed_declared is compressed
    assert evidence.evidence_scope == "XML_METADATA_ONLY"
    assert evidence.native_compatibility == "NOT_VERIFIED"
    assert evidence.payload_verified is False


def test_cli_reports_metadata_only(tmp_path):
    path = tmp_path / "fake.sps"
    path.write_bytes(make_container())
    result = subprocess.run([sys.executable, "-m", "vclone.sps_probe", str(path)],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    obj = json.loads(result.stdout)
    assert obj["native_compatibility"] == "NOT_VERIFIED"
    assert obj["payload_verified"] is False
    assert "{}" not in result.stdout


@pytest.mark.parametrize("mutate", [
    lambda b: b.replace(b'binOffset="', b'binOffset="9', 1),
    lambda b: b.replace(b'binSize="2"', b'binSize="-2"', 1),
    lambda b: b.replace(b'binSizeRaw="2"', b'binSizeRaw="999999999999999999999"', 1),
    lambda b: b.replace(b'bCompressed="0"', b'bCompressed="yes"', 1),
    lambda b: b + b"TRAILING",
    lambda b: b[:-1],
    lambda b: b.replace(b"<File ", b"<F!le ", 1),
    lambda b: b.replace(b'encoding="UTF-8"', b'encoding="UF8-8"', 1),
])
def test_invalid_metadata_and_boundaries_rejected(mutate):
    data = mutate(make_container())
    with pytest.raises(ValueError):
        sps_probe.inspect_prefix(data, len(data))


def test_oversized_header_and_size_denied():
    data = make_container()
    with pytest.raises(ValueError, match="oversized"):
        sps_probe.inspect_prefix(data + b" " * sps.MAX_HEADER_BYTES,
                                 len(data) + sps.MAX_HEADER_BYTES)
    with pytest.raises(ValueError, match="oversized"):
        sps_probe.inspect_prefix(data, sps.MAX_CONTAINER_BYTES + 1)


def test_dtd_and_duplicate_data_rejected():
    data = make_container()
    malicious = data.replace(b"<VIOSO>", b'<!DOCTYPE VIOSO [<!ENTITY x "abc">]><VIOSO>', 1)
    with pytest.raises(ValueError, match="DTD"):
        sps_probe.inspect_prefix(malicious, len(malicious))
    duplicate = data.replace(b"</VIOSO>", b'<data binOffset="00000000000000000100"/></VIOSO>', 1)
    with pytest.raises(ValueError, match="shape"):
        sps_probe.inspect_prefix(duplicate, len(duplicate))


def test_metadata_only_never_reads_payload(tmp_path, monkeypatch):
    path = tmp_path / "large.sps"
    secret_payload = b"\x00PRIVATE_PAYLOAD_NOT_TO_READ"
    data = make_container(secret_payload)
    path.write_bytes(data)
    observed = bytearray()
    original = sps_probe.os.read

    def guarded_read(fd, length):
        assert length == 1, "bulk read risks crossing into the binary payload"
        chunk = original(fd, length)
        observed.extend(chunk)
        return chunk

    monkeypatch.setattr(sps_probe.os, "read", guarded_read)
    info = sps_probe.inspect_file(path)
    assert info.file_bytes == len(data)
    assert len(observed) == info.bin_offset
    assert bytes(observed) == data[:info.bin_offset]
    assert secret_payload not in observed


def test_sparse_oversized_file_fails_before_any_read(tmp_path, monkeypatch):
    path = tmp_path / "oversized.sps"
    with path.open("wb") as handle:
        handle.truncate(sps.MAX_CONTAINER_BYTES + 1)

    def deny_read(*args, **kwargs):
        raise AssertionError("must not read oversized file")

    monkeypatch.setattr(sps_probe.os, "read", deny_read)
    with pytest.raises(ValueError, match="oversized"):
        sps_probe.inspect_file(path)


def test_nonregular_paths_rejected(tmp_path):
    with pytest.raises(ValueError, match="regular"):
        sps_probe.inspect_file(tmp_path)
    path = tmp_path / "original.sps"
    path.write_bytes(make_container())
    alias = tmp_path / "alias.sps"
    try:
        alias.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not available here")
    with pytest.raises(ValueError, match="symlink"):
        sps_probe.inspect_file(alias)


def test_unknown_header_not_misclassified_as_native():
    data = make_container()
    assert sps_probe.inspect_prefix(data, len(data)).native_compatibility == "NOT_VERIFIED"


def test_spoofed_bin_offset_in_xml_comment_does_not_control_read_limit(tmp_path, monkeypatch):
    original_header = sps._header(0, 2, 2, False)
    deceptive_comment = b'  <!-- binOffset="00000000000000065530" -->\n'
    header = original_header.replace(b'  <File ', deceptive_comment + b'  <File ', 1)
    actual_offset = len(header)
    header = header.replace(
        b'<data binOffset="00000000000000000000"',
        b'<data binOffset="' + f'{actual_offset:020d}'.encode() + b'"', 1
    )
    source = tmp_path / "comment.sps"
    source.write_bytes(header + b"{}")
    observed = bytearray()
    real_read = sps_probe.os.read

    def capture_read(fd, size):
        value = real_read(fd, size)
        observed.extend(value)
        return value

    monkeypatch.setattr(sps_probe.os, "read", capture_read)
    evidence = sps_probe.inspect_file(source)
    assert evidence.bin_offset == actual_offset
    assert bytes(observed) == header
    assert len(observed) == actual_offset
