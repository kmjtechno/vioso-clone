"""Read-only P520 Windows desktop rig preflight for operator optical QA.

Never opens cameras, projectors, windows, streams or network connections;
never guesses which display is a projector or whether its power is ON.
Only enumerates the process's current Windows desktop rectangles, and
optionally checks a private camera profile offline without exposing secrets.
"""
from __future__ import annotations

import sys

MAX_DISPLAYS = 16


class RigPreflightError(ValueError):
    """Display-session inspection unavailable or unsafe for projection."""


def _rectangles_overlap(a, b):
    return (
        min(a["right"], b["right"]) > max(a["left"], b["left"])
        and min(a["bottom"], b["bottom"]) > max(a["top"], b["top"])
    )


def report_display_layout(records, *, expected_projectors=2):
    """Normalize Win32 screen rectangles; do not infer attached projector IDs.

    Pure data processing so synthetic and Windows CI can test the exact same
    acceptance gates. An extended-desktop layout is not proof of power state.
    """
    if type(expected_projectors) is not int or not 1 <= expected_projectors <= 8:
        raise RigPreflightError("expected projector count must be 1..8")
    if not isinstance(records, (tuple, list)) or not 1 <= len(records) <= MAX_DISPLAYS:
        raise RigPreflightError("desktop must report 1..16 display rectangles")
    result = []
    for i, obj in enumerate(records):
        if not isinstance(obj, dict) or set(obj) != {
            "left", "top", "right", "bottom", "primary"
        }:
            raise RigPreflightError("invalid desktop rectangle record")
        if any(type(obj[k]) is not int or abs(obj[k]) > 32768
               for k in ("left", "top", "right", "bottom")):
            raise RigPreflightError("desktop rectangle coordinates out of safe bounds")
        if type(obj["primary"]) is not bool:
            raise RigPreflightError("desktop primary flag must be boolean")
        width = obj["right"] - obj["left"]
        height = obj["bottom"] - obj["top"]
        if not 64 <= width <= 8192 or not 64 <= height <= 8192:
            raise RigPreflightError("desktop rectangle dimensions are not valid")
        result.append({
            "display_index": i,
            "x": obj["left"],
            "y": obj["top"],
            "width": width,
            "height": height,
            "primary": obj["primary"],
        })
    if sum(d["primary"] for d in result) != 1:
        raise RigPreflightError("desktop must report exactly one primary display")
    overlapping = []
    for i, left in enumerate(records):
        for j in range(i + 1, len(records)):
            if _rectangles_overlap(left, records[j]):
                overlapping.append([i, j])
    enough = len(result) >= expected_projectors + 1
    if overlapping:
        readiness = "BLOCKED_MIRRORED_OR_OVERLAPPING_DESKTOPS"
    elif not enough:
        readiness = "BLOCKED_INSUFFICIENT_EXTENDED_DESKTOPS"
    else:
        readiness = "OPERATOR_MAPPING_REQUIRED"
    return {
        "schema": "kmj.rig.display-preflight.v1",
        "read_only": True,
        "projector_power_state": "NOT_VERIFIED",
        "projector_identity": "NOT_VERIFIED",
        "camera_connection": "NOT_TESTED",
        "hardware_optical_acceptance": "NOT_VERIFIED",
        "expected_projectors": expected_projectors,
        "desktop_displays_found": len(result),
        "desktop_rectangles": result,
        "overlapping_display_pairs": overlapping,
        "display_layout_gate": readiness,
        "next_step": (
            "OPERATOR_CONFIRM_PHYSICAL_PROJECTOR_TO_DISPLAY_MAPPING"
            if readiness == "OPERATOR_MAPPING_REQUIRED"
            else "CHECK_WINDOWS_EXTEND_DISPLAY_CONFIGURATION"
        ),
    }


def enumerate_windows_displays():
    """Use read-only Win32 EnumDisplayMonitors/GetMonitorInfoW in this session."""
    if sys.platform != "win32":
        raise RigPreflightError("display inventory requires a Windows desktop session")
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG), ("top", wintypes.LONG),
            ("right", wintypes.LONG), ("bottom", wintypes.LONG),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
        ctypes.POINTER(RECT), wintypes.LPARAM)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_info = user32.GetMonitorInfoW
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW)]
    get_info.restype = wintypes.BOOL
    enumerate_monitors = user32.EnumDisplayMonitors
    enumerate_monitors.argtypes = [
        wintypes.HDC, ctypes.POINTER(RECT), callback_type, wintypes.LPARAM
    ]
    enumerate_monitors.restype = wintypes.BOOL
    screens = []
    failed = [False]

    @callback_type
    def visit(handle, _device_context, _rectangle, _private):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if not get_info(handle, ctypes.byref(info)):
            failed[0] = True
            return False
        rect = info.rcMonitor
        screens.append({
            "left": int(rect.left), "top": int(rect.top),
            "right": int(rect.right), "bottom": int(rect.bottom),
            "primary": bool(info.dwFlags & 1),
        })
        # Keep enumerating; reject an oversized list after the Win32 call,
        # rather than treating a normal callback stop as an API failure.
        return True

    ok = enumerate_monitors(None, None, visit, 0)
    if failed[0] or not ok or not screens:
        raise RigPreflightError("Windows monitor enumeration failed or was truncated")
    # Native Win32 callback order is not guaranteed; put primary first then
    # sort by desktop location for a deterministic, non-identifying receipt.
    return sorted(screens, key=lambda d: (
        not d["primary"], d["top"], d["left"], d["bottom"], d["right"]
    ))


def rig_preflight(*, expected_projectors=2, camera_profile=None):
    """Offline read-only report; camera profile only undergoes schema checks."""
    result = report_display_layout(
        enumerate_windows_displays(), expected_projectors=expected_projectors)
    if camera_profile is not None:
        from .camera_sources import read_profile, profile_status
        result["camera_profile"] = profile_status(read_profile(camera_profile))
    else:
        result["camera_profile"] = {
            "source_validation": "NOT_CHECKED",
            "camera_connection": "NOT_TESTED",
        }
    return result
