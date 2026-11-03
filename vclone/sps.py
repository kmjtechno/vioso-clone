"""Clone's own .sps container (XML header + binary tail).

VERIFIED from the original DLL (see docs/re_notes_sps_dll.md): XML root <VIOSO> with a
<File version build/> child; blobs referenced by a <data> node carrying binOffset (20-digit
zero-padded), binSize, binSizeRaw, bCompressed; zlib is available (bUseCompressedXmlFiles /
iCompressLevel); default name SPSet_XML_YYMMDD_hhmmss_mmm.sps.
INFERRED/own choices: payload = the clone's project JSON, raw zlib when compressed, blob
appended directly after the XML text. Not byte-compatible with the original.
"""
from __future__ import annotations

import datetime
import json
import re
import zlib
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree as ET

VERSION = "1.0.0"
BUILD = 1


def default_filename(now: datetime.datetime | None = None) -> str:
    n = now or datetime.datetime.now()
    return "SPSet_XML_%02d%02d%02d_%02d%02d%02d_%03d.sps" % (
        n.year % 100, n.month, n.day, n.hour, n.minute, n.second, n.microsecond // 1000)


def _header(offset: int, size: int, raw: int, compressed: bool) -> bytes:
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<VIOSO>\n'
           f'  <File version="{VERSION}" build="{BUILD}"/>\n'
           f'  <data binOffset="{offset:020d}" binSize="{size}" binSizeRaw="{raw}" '
           f'bCompressed="{int(compressed)}"/>\n</VIOSO>\n')
    return xml.encode("utf-8")


# Defensive limits for untrusted clone-container files. These are policy bounds for
# the independent clone format, not claims about native VIOSO file limits.
MAX_HEADER_BYTES = 64 * 1024
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_RAW_BYTES = 64 * 1024 * 1024
MAX_CONTAINER_BYTES = MAX_HEADER_BYTES + MAX_PAYLOAD_BYTES


def dumps(project, compress: bool = True, level: int = 6) -> bytes:
    if type(level) is not int or not 0 <= level <= 9:
        raise ValueError("compression level must be an integer in 0..9")
    raw = json.dumps(asdict(project)).encode("utf-8")
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("project is too large for the .sps container")
    blob = zlib.compress(raw, level) if compress else raw
    if len(blob) > MAX_PAYLOAD_BYTES:
        raise ValueError("payload is too large for the .sps container")
    offset = len(_header(0, len(blob), len(raw), compress))  # fixed-width offset => length stable
    return _header(offset, len(blob), len(raw), compress) + blob


def _unsigned_attr(node, name: str, maximum: int) -> int:
    value = node.get(name)
    if value is None or re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError(f"malformed .sps: invalid {name}")
    number = int(value)
    if number > maximum:
        raise ValueError(f"malformed .sps: {name} exceeds size limit")
    return number


def loads(data: bytes):
    from .configs import CameraIntrinsics
    from .project import Project

    if not isinstance(data, (bytes, bytearray)) or len(data) > MAX_CONTAINER_BYTES:
        raise ValueError("invalid or oversized .sps container")
    # Only scan the bounded XML prefix, not an arbitrary-sized binary payload.
    m = re.search(rb"</VIOSO>\s*", data[:MAX_HEADER_BYTES])
    if not m or not data.startswith(b"<?xml"):
        raise ValueError("not a .sps file (no <VIOSO> header)")
    try:
        root = ET.fromstring(data[:m.end()])
    except ET.ParseError:
        raise ValueError("malformed .sps XML") from None
    node = root.find("data")
    if root.tag != "VIOSO" or root.find("File") is None or node is None or len(root.findall("data")) != 1:
        raise ValueError("malformed .sps header")

    offset_text = node.get("binOffset")
    if offset_text is None or re.fullmatch(r"[0-9]{20}", offset_text) is None:
        raise ValueError("malformed .sps: binOffset must be 20 decimal digits")
    off = int(offset_text)
    if off > MAX_HEADER_BYTES:
        raise ValueError("malformed .sps: header exceeds size limit")
    size = _unsigned_attr(node, "binSize", MAX_PAYLOAD_BYTES)
    rawsize = _unsigned_attr(node, "binSizeRaw", MAX_RAW_BYTES)
    compressed = node.get("bCompressed")
    if compressed not in ("0", "1"):
        raise ValueError("malformed .sps: invalid compression flag")
    if off != m.end():
        raise ValueError(f"malformed .sps: binOffset {off} != XML boundary {m.end()}")
    if off + size != len(data):
        raise ValueError("truncated or trailing .sps payload")

    blob = data[off:off + size]
    if compressed == "1":
        decoder = zlib.decompressobj()
        try:
            # A dishonest binSizeRaw cannot trigger unbounded decompression.
            raw = decoder.decompress(blob, rawsize + 1)
        except zlib.error:
            raise ValueError("invalid .sps compressed payload") from None
        if (len(raw) != rawsize or not decoder.eof or decoder.unused_data
                or decoder.unconsumed_tail):
            raise ValueError("compressed .sps payload size or stream mismatch")
    else:
        raw = blob
        if len(raw) != rawsize:
            raise ValueError("payload size mismatch")
    try:
        project_data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("invalid .sps project JSON") from None
    if not isinstance(project_data, dict):
        raise ValueError("invalid .sps project JSON root")

    cam = project_data.get("camera")
    try:
        return Project(project_data.get("name", "untitled"),
                       CameraIntrinsics(**cam) if cam else None,
                       project_data.get("content_space", ""),
                       project_data.get("displays", []),
                       project_data.get("steps_done", []),
                       project_data.get("scan", {}),
                       project_data.get("result", {}))
    except (TypeError, ValueError):
        raise ValueError("invalid .sps project fields") from None


def save(project, path, compress: bool = True) -> None:
    Path(path).write_bytes(dumps(project, compress))


def load(path):
    source = Path(path)
    if source.stat().st_size > MAX_CONTAINER_BYTES:
        raise ValueError("oversized .sps file")
    return loads(source.read_bytes())
