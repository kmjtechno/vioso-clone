"""Bounded, read-only evidence from a VIOSO-like .sps XML header.

This is a metadata inspector, NOT a native VIOSO 7 loader or compatibility
checker. It deliberately never reads, decompresses, or interprets the payload.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import stat
import sys
from xml.etree import ElementTree as ET

from . import sps


@dataclass(frozen=True)
class SPSHeaderEvidence:
    xml_root: str
    file_version: str | None
    file_build: str | None
    bin_offset: int
    bin_size: int
    bin_size_raw: int
    compressed_declared: bool
    file_bytes: int
    evidence_scope: str = "XML_METADATA_ONLY"
    payload_verified: bool = False
    native_compatibility: str = "NOT_VERIFIED"


def _declared_uint(node: ET.Element, attribute: str, maximum: int) -> int:
    value = node.get(attribute)
    if value is None or len(value) > 20 or re.fullmatch(r"[0-9]+", value) is None:
        raise ValueError(f"invalid .sps {attribute}")
    number = int(value)
    if number > maximum:
        raise ValueError(f".sps {attribute} exceeds inspection limit")
    return number


def _display_attr(node: ET.Element, attribute: str) -> str | None:
    value = node.get(attribute)
    if value is None:
        return None
    if len(value) > 64 or not value.isprintable():
        raise ValueError(f"invalid .sps {attribute}")
    return value


def inspect_prefix(prefix: bytes, file_bytes: int) -> SPSHeaderEvidence:
    """Inspect at most 64 KiB of header metadata for a known on-disk file size.

    file_bytes must be obtained from a trusted file descriptor; this function
    performs structural checks only and never validates native compatibility.
    """
    if not isinstance(prefix, bytes) or len(prefix) > sps.MAX_HEADER_BYTES:
        raise ValueError("invalid or oversized XML header prefix")
    if type(file_bytes) is not int or not 0 <= file_bytes <= sps.MAX_CONTAINER_BYTES:
        raise ValueError("invalid or oversized .sps file size")
    if not prefix.startswith(b"<?xml"):
        raise ValueError("missing .sps XML declaration")
    match = re.search(rb"</VIOSO>[\x20\x09\x0a\x0d]*", prefix)
    if match is None:
        raise ValueError("missing .sps XML closing tag within header limit")
    header = prefix[:match.end()]
    if b"<!DOCTYPE" in header.upper() or b"<!ENTITY" in header.upper():
        raise ValueError("XML DTD/entities are not accepted")
    try:
        root = ET.fromstring(header)
    except (ET.ParseError, LookupError):
        raise ValueError("invalid .sps XML header") from None
    file_nodes, data_nodes = root.findall("File"), root.findall("data")
    if root.tag != "VIOSO" or len(file_nodes) != 1 or len(data_nodes) != 1:
        raise ValueError("unsupported .sps XML header shape")
    node = data_nodes[0]
    text_offset = node.get("binOffset")
    if text_offset is None or re.fullmatch(r"[0-9]{20}", text_offset) is None:
        raise ValueError("invalid .sps binOffset width")
    offset = int(text_offset)
    size = _declared_uint(node, "binSize", sps.MAX_PAYLOAD_BYTES)
    raw = _declared_uint(node, "binSizeRaw", sps.MAX_RAW_BYTES)
    flag = node.get("bCompressed")
    if flag not in ("0", "1"):
        raise ValueError("invalid .sps compression flag")
    if offset != match.end():
        raise ValueError(".sps binOffset does not match XML boundary")
    if offset + size != file_bytes:
        raise ValueError(".sps declared payload does not match file size")
    if flag == "0" and size != raw:
        raise ValueError("uncompressed .sps declared size mismatch")
    file_node = file_nodes[0]
    return SPSHeaderEvidence(
        xml_root="VIOSO",
        file_version=_display_attr(file_node, "version"),
        file_build=_display_attr(file_node, "build"),
        bin_offset=offset, bin_size=size, bin_size_raw=raw,
        compressed_declared=flag == "1", file_bytes=file_bytes,
    )


def inspect_file(path: str | os.PathLike[str]) -> SPSHeaderEvidence:
    """Inspect a regular non-symlink file without reading the binary payload."""
    source = Path(path)
    if source.is_symlink():
        raise ValueError("symlink .sps paths are not inspected")
    # Windows may reject opening a directory before fstat can classify it.
    # Guard special paths first, then recheck the opened file descriptor.
    if not source.is_file():
        raise ValueError("only regular .sps files can be inspected")
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0)
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    fd = os.open(source, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("only regular .sps files can be inspected")
        if before.st_size > sps.MAX_CONTAINER_BYTES:
            raise ValueError("oversized .sps file")
        prefix = os.read(fd, min(before.st_size, sps.MAX_HEADER_BYTES))
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError(".sps file changed while being inspected")
        return inspect_prefix(prefix, before.st_size)
    finally:
        os.close(fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only .sps XML metadata probe; native support NOT VERIFIED")
    parser.add_argument("file", help="Path to an owner-authorized .sps file")
    args = parser.parse_args(argv)
    try:
        evidence = inspect_file(args.file)
    except (OSError, ValueError) as exc:
        print(f"sps probe refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(evidence), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
