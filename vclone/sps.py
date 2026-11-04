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


def dumps(project, compress: bool = True, level: int = 6) -> bytes:
    raw = json.dumps(asdict(project)).encode("utf-8")
    blob = zlib.compress(raw, level) if compress else raw
    offset = len(_header(0, len(blob), len(raw), compress))  # fixed-width offset => length stable
    return _header(offset, len(blob), len(raw), compress) + blob


def loads(data: bytes):
    from .configs import CameraIntrinsics
    from .project import Project
    m = re.search(rb"</VIOSO>\s*", data)
    if not m or not data.lstrip().startswith(b"<?xml"):
        raise ValueError("not a .sps file (no <VIOSO> header)")
    root = ET.fromstring(data[:m.end()])
    node = root.find("data")
    if root.tag != "VIOSO" or root.find("File") is None or node is None:
        raise ValueError("malformed .sps header")
    try:
        off, size, rawsize = int(node.get("binOffset")), int(node.get("binSize")), int(node.get("binSizeRaw"))
        comp = node.get("bCompressed") == "1"
    except (TypeError, ValueError):
        raise ValueError("malformed .sps data node") from None
    if off != m.end():
        raise ValueError(f"malformed .sps: binOffset {off} != XML boundary {m.end()}")
    blob = data[off:off + size]
    if len(blob) != size:
        raise ValueError("truncated .sps payload")
    raw = zlib.decompress(blob) if comp else blob
    if len(raw) != rawsize:
        raise ValueError("payload size mismatch")
    d = json.loads(raw.decode("utf-8"))
    cam = d.get("camera")
    return Project(d.get("name", "untitled"), CameraIntrinsics(**cam) if cam else None,
                   d.get("content_space", ""), d.get("displays", []), d.get("steps_done", []),
                   d.get("scan", {}), d.get("result", {}))


def save(project, path, compress: bool = True) -> None:
    Path(path).write_bytes(dumps(project, compress))


def load(path):
    return loads(Path(path).read_bytes())
