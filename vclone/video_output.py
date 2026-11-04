"""Opt-in bounded CPU-warped local-video playback on one projector window.

This is not a hardware-synchronized renderer or VIOSO/NDI implementation.
The renderer computes the independent clone's mesh warp on each video frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
import os
from pathlib import Path
import stat
import time
from typing import Callable, Iterable

import cv2
import numpy as np

from . import render
from .project import Project, MissingInput

MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
MAX_FRAME_PIXELS = 1920 * 1080
MAX_SECONDS = 30
MAX_FPS = 30
SUPPORTED_SUFFIXES = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})


class VideoPlaybackError(RuntimeError):
    """Unsafe input, decode failure, or physical-output error."""


@dataclass(frozen=True)
class VideoReceipt:
    frames_presented: int
    stopped_by_escape: bool
    source_type: str = "LOCAL_VIDEO"
    hardware_acceptance: str = "NOT_VERIFIED"


def _params(fps, seconds, x, y, confirmed):
    if not confirmed:
        raise VideoPlaybackError("projector confirmation required: --confirm-display")
    if (type(fps) not in (int, float) or not isfinite(fps) or not 1 <= fps <= MAX_FPS
            or type(seconds) not in (int, float) or not isfinite(seconds)
            or not 0 < seconds <= MAX_SECONDS):
        raise ValueError("playback fps or duration exceeds safety bounds")
    if (type(x) is not int or type(y) is not int
            or abs(x) > 32768 or abs(y) > 32768):
        raise ValueError("projector desktop origin is invalid")
    return float(fps), float(seconds)


def _mesh_and_size(project: Project):
    if not isinstance(project, Project) or not project.result.get("mesh"):
        raise MissingInput("run Calibrate before playing video")
    size = project.scan.get("proj_size")
    if (not isinstance(size, (list, tuple)) or len(size) != 2
            or any(type(x) is not int for x in size)
            or not 2 <= size[0] <= 1920 or not 2 <= size[1] <= 1080
            or size[0] * size[1] > MAX_FRAME_PIXELS):
        raise VideoPlaybackError("unsupported projector output dimensions")
    try:
        mesh = np.asarray(project.result["mesh"], dtype=np.float64)
        if mesh.ndim != 3 or mesh.shape[2] != 2 or min(mesh.shape[:2]) < 2:
            raise ValueError("invalid mesh")
    except (ValueError, TypeError) as exc:
        raise VideoPlaybackError(f"invalid calibrated mesh: {exc}") from exc
    return mesh, tuple(size)


def _video_source(path):
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_SUFFIXES or path.is_symlink():
        raise VideoPlaybackError("only regular non-symlink local video files are supported")
    try:
        info = path.stat()
    except OSError as exc:
        raise VideoPlaybackError(f"video unavailable: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_VIDEO_BYTES:
        raise VideoPlaybackError("video must be a nonempty regular file under 4 GiB")
    return path


def warp_frames(
    project: Project,
    frames: Iterable[np.ndarray],
    show: Callable[[np.ndarray], None],
    wait: Callable[[int], int],
    *,
    fps: float = 24,
    seconds: float = 10,
    clock: Callable[[], float] = time.monotonic,
) -> VideoReceipt:
    """Testable bounded stream. show/wait may be a fake display in CI."""
    if (type(fps) not in (int, float) or not isfinite(fps) or not 1 <= fps <= MAX_FPS
            or type(seconds) not in (int, float) or not isfinite(seconds)
            or not 0 < seconds <= MAX_SECONDS):
        raise ValueError("unsafe playback fps/duration")
    if not callable(show) or not callable(wait) or not callable(clock):
        raise TypeError("show, wait and clock must be callable")
    mesh, size = _mesh_and_size(project)
    limit = max(1, ceil(fps * seconds))
    start = clock()
    count = 0
    escaped = False
    iterator = iter(frames)
    while count < limit:
        if clock() - start > seconds:
            break
        try:
            frame = next(iterator)
        except StopIteration:
            break
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                or frame.ndim != 3 or frame.shape[2] != 3
                or frame.shape[0] < 2 or frame.shape[1] < 2
                or frame.shape[0] * frame.shape[1] > MAX_FRAME_PIXELS):
            raise VideoPlaybackError("invalid camera/video frame format or dimensions")
        warped = render.render_projector(frame, mesh, size)
        show(warped)
        count += 1
        delay = max(1, min(1000, int((start + count / fps - clock()) * 1000)))
        if (wait(delay) & 0xFF) == 27:
            escaped = True
            break
        if clock() - start > seconds:
            break
    if not count:
        raise VideoPlaybackError("video contains no decodable frames")
    return VideoReceipt(count, escaped)


def play_file(
    project: Project, source, *, projector_x: int, projector_y: int,
    fps: float = 24, seconds: float = 10, confirmed: bool = False,
) -> VideoReceipt:
    """Display an explicitly approved local video on one projector and close it."""
    fps, seconds = _params(fps, seconds, projector_x, projector_y, confirmed)
    _mesh_and_size(project)
    path = _video_source(source)
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise VideoPlaybackError("cannot decode the local video")
    name = "KMJ Calibrated Video Preview"
    created = False
    try:
        cv2.namedWindow(name, cv2.WINDOW_NORMAL)
        created = True
        cv2.moveWindow(name, projector_x, projector_y)
        cv2.setWindowProperty(name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        def frames():
            while True:
                ok, image = capture.read()
                if not ok or image is None:
                    return
                yield image

        return warp_frames(
            project, frames(), lambda image: cv2.imshow(name, image),
            lambda duration: cv2.waitKey(duration), fps=fps, seconds=seconds
        )
    finally:
        capture.release()
        if created:
            cv2.destroyWindow(name)
