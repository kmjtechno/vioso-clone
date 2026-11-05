"""Camera-agnostic input profiles for independent optical calibration.

The source protocol is selected explicitly; the software never discovers,
logs, scans or connects to a network camera without operator action. A
registered SDK adapter allows future machine-vision/GenICam support without
assuming every proprietary camera is automatically compatible.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit

import cv2

SCHEMA = "kmj.camera.source.v1"
MAX_PROFILE_BYTES = 16384
MAX_URL_LENGTH = 2048
MAX_REPLAY_BYTES = 16 * 1024 ** 3
NETWORK_TYPES = {"rtsp", "rtsps", "onvif_rtsp", "http_mjpeg", "https_mjpeg"}
TYPES = NETWORK_TYPES | {"usb", "video_file", "sdk", "onvif"}
BACKENDS = {"auto", "dshow", "msmf", "ffmpeg", "gstreamer"}


class CameraSourceError(ValueError):
    """Camera profile or selected capture backend was rejected."""


def _safe_path(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise CameraSourceError("camera replay path must be a bounded string")
    p = Path(value)
    if (not p.is_absolute() or p.is_symlink() or p.parent.is_symlink()
            or not p.is_file()):
        raise CameraSourceError("replay must be an existing absolute non-symlink file")
    try:
        info = p.stat()
    except OSError as exc:
        raise CameraSourceError("replay file cannot be inspected") from exc
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_REPLAY_BYTES:
        raise CameraSourceError("replay file is empty or exceeds 16 GiB")
    return str(p)


def validate_profile(data):
    """Check a single source profile without opening cameras or making requests.

    URLs may contain local credentials but are NEVER returned in diagnostics.
    Keep any credential-bearing profile protected on the P520; do not share it.
    """
    if not isinstance(data, dict) or set(data) != {
        "schema", "type", "source", "backend"
    } or data.get("schema") != SCHEMA:
        raise CameraSourceError("invalid camera source profile schema")
    kind = data["type"]
    backend = data["backend"]
    value = data["source"]
    if not isinstance(kind, str) or kind not in TYPES:
        raise CameraSourceError("unsupported camera type: adapter required")
    if backend not in BACKENDS:
        raise CameraSourceError("unrecognized capture backend")
    if kind == "usb":
        if type(value) is not int or not 0 <= value <= 15:
            raise CameraSourceError("USB camera index must be 0..15")
        if backend not in ("auto", "dshow", "msmf", "gstreamer"):
            raise CameraSourceError("USB camera backend incompatible")
    elif kind == "onvif":
        # Control-plane ONVIF profile is an owner-managed LOCAL record, not
        # a guessed RTSP URL; reading it offline never opens a network socket.
        from .onvif_client import validate_source
        validate_source(value)
        if backend not in ("auto", "ffmpeg"):
            raise CameraSourceError("ONVIF Media1 requires FFmpeg capture backend")
    elif kind in NETWORK_TYPES:
        if (not isinstance(value, str) or not 6 <= len(value) <= MAX_URL_LENGTH
                or any(ord(c) < 33 or ord(c) == 127 for c in value)):
            raise CameraSourceError("invalid network camera source URL")
        try:
            parsed = urlsplit(value)
            # Also validates invalid TCP port numbers in any scheme.
            port = parsed.port
        except ValueError as exc:
            raise CameraSourceError("invalid network camera host/port") from exc
        expected = ("rtsp" if kind in ("rtsp", "onvif_rtsp") else
                    "rtsps" if kind == "rtsps" else
                    "http" if kind == "http_mjpeg" else "https")
        if (parsed.scheme != expected or not parsed.hostname
                or parsed.fragment or port == 0):
            raise CameraSourceError("network camera URL scheme or host mismatch")
        if backend not in ("auto", "ffmpeg", "gstreamer"):
            raise CameraSourceError("network camera backend requires FFmpeg or GStreamer")
    elif kind == "video_file":
        _safe_path(value)
        if backend not in ("auto", "ffmpeg", "gstreamer"):
            raise CameraSourceError("replay backend must be FFmpeg or GStreamer")
    else:
        if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value)
                or backend != "auto"):
            raise CameraSourceError("SDK device requires registered safe adapter")
    return {"schema": SCHEMA, "type": kind, "source": value, "backend": backend}


def read_profile(path):
    """Load a bounded private JSON file without exposing embedded stream URIs."""
    p = Path(path)
    if p.is_symlink() or p.parent.is_symlink() or not p.is_file():
        raise CameraSourceError("camera profile must be a regular non-symlink JSON file")
    try:
        info = p.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_PROFILE_BYTES:
            raise CameraSourceError("camera profile must be under 16 KiB")
        data = json.loads(
            p.read_text(encoding="utf-8"),
            parse_constant=lambda _k: (_ for _ in ()).throw(
                CameraSourceError("non-finite camera profile")))
        return validate_profile(data)
    except (UnicodeError, OSError, ValueError) as exc:
        # Error messages must never echo a URL, username or password.
        if isinstance(exc, CameraSourceError):
            raise
        raise CameraSourceError("camera profile unreadable or invalid JSON") from None


def profile_status(profile):
    """Credential-safe offline compatibility report, not an online claim."""
    data = validate_profile(profile)
    return {
        "schema": "kmj.camera.profile-check.v1",
        "camera_type": data["type"],
        "capture_backend": data["backend"],
        "source_validation": "PASS",
        "camera_connection": "NOT_TESTED",
        "camera_frame_quality": "NOT_VERIFIED",
        "native_vioso7_compatibility": "NOT_VERIFIED",
        "no_network_or_camera_access": True,
    }


def _api_backend(name, *, kind):
    if name == "auto":
        name = "ffmpeg" if kind in NETWORK_TYPES | {"video_file", "onvif"} else "auto"
    names = {
        "auto": "CAP_ANY", "dshow": "CAP_DSHOW", "msmf": "CAP_MSMF",
        "ffmpeg": "CAP_FFMPEG", "gstreamer": "CAP_GSTREAMER",
    }
    key = names[name]
    if not hasattr(cv2, key):
        raise CameraSourceError("selected OpenCV camera backend unavailable")
    return getattr(cv2, key)


def open_camera(profile, *, sdk_adapters=None):
    """Open ONLY a user-selected source; caller must always release() it.

    RTSP/HTTP inputs demand OpenCV's timeout-capable backend. SDK support is
    explicit injection from installed trusted code, never dynamic imports.
    """
    data = validate_profile(profile)
    kind = data["type"]
    if kind == "sdk":
        adapters = sdk_adapters or {}
        factory = adapters.get(data["source"])
        if not callable(factory):
            raise CameraSourceError("selected camera SDK adapter is not installed")
        stream = factory()
    elif kind == "usb":
        value = data["source"]
        backend = _api_backend(data["backend"], kind=kind)
        stream = cv2.VideoCapture(value) if backend == cv2.CAP_ANY else cv2.VideoCapture(value, backend)
    else:
        if kind == "onvif":
            # READ_ONLY ONVIF Media1 negotiation happens only when an already
            # confirmed camera probe/capture explicitly opens this profile.
            # The only emitted video URL is for this selected private camera.
            from .onvif_client import resolve_stream_uri
            try:
                value = resolve_stream_uri(data["source"])
            except Exception:
                # urllib, native XML parsers and optional video backends can
                # embed the camera host or password in an exception. Never
                # echo arbitrary failure messages from this trust boundary.
                raise CameraSourceError(
                    "selected private ONVIF media stream could not be resolved") from None
        else:
            value = _safe_path(data["source"]) if kind == "video_file" else data["source"]
        backend = _api_backend(data["backend"], kind=kind)
        if kind in NETWORK_TYPES | {"onvif"}:
            # Bounded open/read support, without fallback to unbounded network
            # VideoCapture on systems missing this capability.
            if (not hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC")
                    or not hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC")):
                raise CameraSourceError("network camera backend has no bounded timeouts")
            timeout = [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 4000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 4000,
            ]
            try:
                stream = cv2.VideoCapture(value, backend, timeout)
            except (TypeError, cv2.error):
                raise CameraSourceError("network camera backend cannot enforce timeouts") from None
        else:
            stream = cv2.VideoCapture(value, backend)
    try:
        if not stream.isOpened():
            stream.release()
            raise CameraSourceError("selected camera source is not available")
    except CameraSourceError:
        raise
    except Exception as exc:
        try:
            stream.release()
        except Exception:
            pass
        raise CameraSourceError("camera adapter failed to initialize safely") from None
    return stream
