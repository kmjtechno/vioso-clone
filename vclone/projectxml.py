"""Project settings XML (clone dialect).

Structure follows docs/re_notes_sps.md section 1 (root VIOSO > project > property nodes,
field names, defaults and ranges). Whether the original reads this exactly is NOT verified:
attribute-vs-text placement of items is an anuman there, so this is the clone's own dialect and
makes no compatibility claim. Parsing fails closed on malformed, out-of-range, duplicate or
unknown input.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields

VERSION = "1.0"
CREATOR = "vclone"

_SCREEN_RANGES = {
    "type": (0, 8), "outside": (0, 1),
    "radius": (1, 1e7), "width": (1, 1e7), "height": (1, 1e7),
    "horizontalstep": (1, 1e7), "verticalstep": (1, 1e7),
    "longitudestep": (0.1, 10), "latitudestep": (0.1, 10),
    "leftangle": (-179, 0), "bottomangle": (-179, 0),
    "topangle": (0, 179), "rightangle": (0, 179),
    "latitudestartangle": (0, 179), "latitudeendangle": (0, 179),
}
_INT_SCREEN = {"type", "outside"}
_ENUMS = {"type": (0, 5), "state": (-1, 3), "method": (1, 2)}


def _check(label, value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not lo <= value <= hi:
        raise ValueError(f"{label} out of range [{lo}, {hi}]: {value!r}")


@dataclass
class ScreenParams:
    type: int = 4
    outside: int = 0
    radius: float = 1000
    width: float = 3200
    height: float = 2000
    horizontalstep: float = 100
    verticalstep: float = 100
    longitudestep: float = 2
    latitudestep: float = 2
    leftangle: float = -90
    bottomangle: float = -45
    topangle: float = 45
    rightangle: float = 90
    latitudestartangle: float = 0
    latitudeendangle: float = 90

    def __post_init__(self):
        for name, (lo, hi) in _SCREEN_RANGES.items():
            v = getattr(self, name)
            _check(f"screen.{name}", v, lo, hi)
            if name in _INT_SCREEN and int(v) != v:
                raise ValueError(f"screen.{name} must be an integer: {v!r}")


@dataclass
class ProjectSettings:
    name: str = "untitled"
    type: int = 1
    state: int = 0
    method: int = 1
    spspath: str = "_Startup.sps"
    mrdpath: str = "_Startup.mrd"
    exoptdefpath: str = "SPExtCalibCommOpDef.ini"
    recalibscriptname: str = "stdEdit.ini"
    editscriptname: str = "stdRecal.ini"
    calibratescriptname: str = "stdCal.ini"
    screen: ScreenParams = field(default_factory=ScreenParams)

    def __post_init__(self):
        for name, (lo, hi) in _ENUMS.items():
            v = getattr(self, name)
            _check(name, v, lo, hi)
            if int(v) != v:
                raise ValueError(f"{name} must be an integer: {v!r}")
        for f in fields(self):
            if f.type in ("str", str) and not isinstance(getattr(self, f.name), str):
                raise ValueError(f"{f.name} must be a string")


_TOP = [f.name for f in fields(ProjectSettings) if f.name != "screen"]
_STR = {n for n in _TOP if n not in _ENUMS}


def _prop(parent, name, value, ptype):
    el = ET.SubElement(parent, "property", {"name": name, "type": ptype})
    el.text = repr(value) if ptype == "float" else str(value)


def to_xml(s: ProjectSettings) -> str:
    root = ET.Element("VIOSO")
    proj = ET.SubElement(root, "project", {"version": VERSION, "creator": CREATOR})
    for n in _TOP:
        v = getattr(s, n)
        _prop(proj, n, v, "string" if n in _STR else "int")
    scr = ET.SubElement(proj, "property", {"name": "screen", "type": "composite"})
    for n in _SCREEN_RANGES:
        v = getattr(s.screen, n)
        _prop(scr, n, int(v) if n in _INT_SCREEN else float(v), "int" if n in _INT_SCREEN else "float")
    ET.indent(root)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode")


def _num(text, ptype, label):
    try:
        return int(text) if ptype == "int" else float(text)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: not a valid {ptype}: {text!r}") from None


def from_xml(text: str) -> ProjectSettings:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty project xml")
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("DTD/entities are not accepted")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        raise ValueError(f"malformed xml: {e}") from None
    if root.tag != "VIOSO":
        raise ValueError(f"unexpected root {root.tag!r}")
    proj = root.find("project")
    if proj is None:
        raise ValueError("missing <project>")
    if proj.get("version") != VERSION:
        raise ValueError(f"unsupported project version {proj.get('version')!r}")
    top, screen = {}, {}
    for p in proj.findall("property"):
        name = p.get("name")
        if name == "screen":
            if screen:
                raise ValueError("duplicate property screen")
            for c in p.findall("property"):
                cn = c.get("name")
                if cn not in _SCREEN_RANGES:
                    raise ValueError(f"unknown screen property {cn!r}")
                if cn in screen:
                    raise ValueError(f"duplicate screen property {cn!r}")
                screen[cn] = _num(c.text, c.get("type"), f"screen.{cn}")
        elif name in _TOP:
            if name in top:
                raise ValueError(f"duplicate property {name!r}")
            top[name] = p.text or "" if name in _STR else _num(p.text, p.get("type"), name)
        else:
            raise ValueError(f"unknown property {name!r}")
    return ProjectSettings(**top, screen=ScreenParams(**screen))
