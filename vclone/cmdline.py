"""Parser for the original tool's slash-style command line (see SPEC.md section 4)."""
from __future__ import annotations

from dataclasses import dataclass, field

STEPS = {"Design", "Calibrate", "Edit", "Edit MRD", "Export", "Recalibrate",
         "Activate", "Deactivate", "Configure", "RecoverExport"}
_FLAGS = {"0": "blocked_ui", "1": "suitable_ui", "a": "recalib", "A": "recalib_close",
          "E": "export", "M": "minimized", "R": "autoplay", "V": "verbose", "Z": "zero_display"}
_VALUES = {"D": "confirm_secs", "F": "profile", "I": "adapter", "J": "clamp", "L": "sps",
           "Lang": "lang", "O": "project_path", "P": "json_config", "S": "exchange_dir",
           "X": "ipc_name", "Q": "step"}


@dataclass
class CmdLine:
    flags: set = field(default_factory=set)
    values: dict = field(default_factory=dict)
    close_after: bool | None = None


def parse(argv: list[str]) -> CmdLine:
    out = CmdLine()
    for a in argv:
        if not a.startswith("/") or len(a) < 2:
            raise ValueError(f"bad argument: {a!r}")
        key, sep, val = a[1:].partition(":")
        val = val.strip().strip('"').strip()
        if key == "H":  # value optional
            out.values["script_host"] = val or True
        elif key in _FLAGS and not sep:
            out.flags.add(_FLAGS[key])
        elif key in _VALUES and sep:
            if key == "Q":
                step, _, opt = val.partition(";")
                step = step.strip()
                if step not in STEPS:
                    raise ValueError(f"unknown step: {step!r}")
                out.values["step"] = step
                for item in filter(None, (t.strip() for t in opt.split(";"))):
                    k, _, v = item.partition("=")
                    k, v = k.strip().lower(), v.strip().lower()
                    if k != "closeafter" or v not in ("yes", "no"):
                        raise ValueError(f"bad option: {item!r}")
                    out.close_after = v == "yes"
            elif key in ("D", "J", "Lang"):
                out.values[_VALUES[key]] = int(val)
            else:
                out.values[_VALUES[key]] = val
        else:
            raise ValueError(f"unknown switch: {a!r}")
    return out
