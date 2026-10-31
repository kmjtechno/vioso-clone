"""Readers for the XML-style and INI-style config files shipped with the original tool."""
from __future__ import annotations

import configparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


def _root(path) -> ET.Element:
    return ET.parse(str(path)).getroot()


def _f(node, key, default=0.0) -> float:
    return float(node.get(key, default))


@dataclass
class CameraIntrinsics:
    name: str
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    k1: float = 0.0
    k2: float = 0.0
    k3: float = 0.0
    p1: float = 0.0
    p2: float = 0.0

    @property
    def matrix(self):
        return [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]]

    @property
    def dist_coeffs(self):
        """OpenCV order (k1, k2, p1, p2, k3)."""
        return [self.k1, self.k2, self.p1, self.p2, self.k3]


def load_devices(path) -> list[CameraIntrinsics]:
    out = []
    for cam in _root(path).iter("Camera"):
        res = cam.find("./IntrinsicParameter/Resolution")
        if res is None:
            continue
        fl, pp = res.find("FocalLength"), res.find("PrincipalPoint")
        rd, td = res.find("RadialDistorsion"), res.find("TangentialDistorsion")
        out.append(CameraIntrinsics(
            name=cam.get("Name", ""),
            width=int(res.get("width")), height=int(res.get("height")),
            fx=_f(fl, "X"), fy=_f(fl, "Y"), cx=_f(pp, "X"), cy=_f(pp, "Y"),
            k1=_f(rd, "K1") if rd is not None else 0.0,
            k2=_f(rd, "K2") if rd is not None else 0.0,
            k3=_f(rd, "K3") if rd is not None else 0.0,
            p1=_f(td, "P1") if td is not None else 0.0,
            p2=_f(td, "P2") if td is not None else 0.0,
        ))
    return out


def save_devices(path, cams: list[CameraIntrinsics]) -> None:
    root = ET.Element("VIOSO")
    easy = ET.SubElement(root, "SPeASY")
    ET.SubElement(easy, "File", version="1.0.0")
    devs = ET.SubElement(easy, "InputDevices")
    for c in cams:
        cam = ET.SubElement(devs, "Camera", Name=c.name)
        ip = ET.SubElement(cam, "IntrinsicParameter")
        r = ET.SubElement(ip, "Resolution", width=str(c.width), height=str(c.height))
        ET.SubElement(r, "FocalLength", X=repr(c.fx), Y=repr(c.fy))
        ET.SubElement(r, "PrincipalPoint", X=repr(c.cx), Y=repr(c.cy))
        ET.SubElement(r, "RadialDistorsion", K1=repr(c.k1), K2=repr(c.k2), K3=repr(c.k3))
        ET.SubElement(r, "TangentialDistorsion", P1=repr(c.p1), P2=repr(c.p2))
    ET.indent(root)
    ET.ElementTree(root).write(str(path), encoding="utf-8", xml_declaration=True)


@dataclass
class Part:
    row: int
    col: int
    name: str


@dataclass
class DesktopDisplay:
    name: str
    core: str
    pos_x: int
    pos_y: int
    size_x: int
    size_y: int
    rows: int
    cols: int
    rotation: int
    parts: list[Part] = field(default_factory=list)


@dataclass
class LogicalDisplay:
    name: str
    id_string: str
    protocol: str
    rows: int
    cols: int
    displays: list[dict] = field(default_factory=list)


def load_surface_defs(path):
    """Returns (DesktopDisplay list, LogicalDisplay list). Commented-out samples yield empty lists."""
    root = _root(path)
    desk = []
    for d in root.iter("DesktopDisplay"):
        desk.append(DesktopDisplay(
            d.get("name", ""), d.get("core", ""), int(d.get("posX", 0)), int(d.get("posY", 0)),
            int(d.get("sizeX", 0)), int(d.get("sizeY", 0)), int(d.get("rows", 1)),
            int(d.get("cols", 1)), int(d.get("rotation", 0)),
            [Part(int(p.get("iRow", 0)), int(p.get("iCol", 0)), p.get("name", ""))
             for p in d.findall("Part")]))
    logical = []
    for l in root.iter("logicalDisplay"):
        topo = l.find("topology")
        logical.append(LogicalDisplay(
            l.get("name", ""), l.get("idString", ""), l.get("tProtocol", "native"),
            int(topo.get("rows", 1)) if topo is not None else 1,
            int(topo.get("cols", 1)) if topo is not None else 1,
            [dict(x.attrib) for x in l.findall("display")]))
    return desk, logical


@dataclass
class ContentSpace:
    name: str
    width: int
    height: int
    kind: str
    default_model: tuple | None
    models3d: list[str]


def load_content_spaces(path) -> list[ContentSpace]:
    out = []
    for cs in _root(path).iter("ContentSpace"):
        com, dm = cs.find("Common"), cs.find("DefaultModel")
        out.append(ContentSpace(
            cs.get("Name", ""),
            int(com.get("width", 0)) if com is not None else 0,
            int(com.get("height", 0)) if com is not None else 0,
            com.get("typ", "") if com is not None else "",
            tuple(_f(dm, k) for k in ("left", "top", "right", "bottom")) if dm is not None else None,
            [m.get("Name", "") for m in cs.iter("Model3D")]))
    return out


@dataclass
class MPDisplay:
    name: str
    core: str
    rect: tuple
    use: str


@dataclass
class MPPreset:
    arrangement: str
    calib_space: tuple | None
    canvas: tuple | None
    displays: list[MPDisplay]


def _rect(n):
    return tuple(_f(n, k) for k in ("left", "top", "right", "bottom")) if n is not None else None


def load_mp_presets(path) -> list[MPPreset]:
    out = []
    for p in _root(path).iter("MPPreset"):
        com = p.find("Common")
        out.append(MPPreset(
            com.get("tArrangement", "grid") if com is not None else "grid",
            _rect(p.find("CalibSpace")), _rect(p.find("VirtualCanvas")),
            [MPDisplay(d.get("name", ""), d.get("core", ""), _rect(d), d.get("tUse", "normal"))
             for d in p.findall("Display")]))
    return out


def load_calibrator_ini(path) -> dict[str, dict[str, str]]:
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    cp.read(str(path), encoding="utf-8")
    return {s: {k: v.strip().strip('"') for k, v in cp[s].items()} for s in cp.sections()}
