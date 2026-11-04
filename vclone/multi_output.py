"""Offline per-projector CPU frames and content-space overlap blend evidence.

This creates separate PNG previews, not synchronized physical projector output.
No vendor formats or GPU device code are accessed.
"""
from __future__ import annotations

import hashlib
import json
from math import isfinite
from pathlib import Path
import stat

import cv2
import numpy as np

from . import calib, render, color_balance
from .project import Project

MAX_PROJECTORS = 8
MAX_CONTENT_PIXELS = 4096 * 2160
MAX_OUTPUT_PIXELS = 1920 * 1080
MAX_SOURCE_BYTES = 128 * 1024 * 1024


class MultiExportError(ValueError):
    """Invalid project bundle or unsafe file operation."""


def _validated_source(path):
    path = Path(path)
    if path.is_symlink():
        raise MultiExportError("content image symlinks are not accepted")
    try:
        info = path.stat()
    except OSError as exc:
        raise MultiExportError(f"content image not available: {exc}") from exc
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_SOURCE_BYTES:
        raise MultiExportError("content image must be a regular file under 128 MiB")
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise MultiExportError("cannot decode BGR content image")
    h, w = image.shape[:2]
    if w < 2 or h < 2 or w > 4096 or h > 2160 or w * h > MAX_CONTENT_PIXELS:
        raise MultiExportError("content dimensions exceed preview safety bounds")
    return image


def _validated_mesh(project, content_size):
    if not isinstance(project, Project) or not isinstance(project.scan, dict):
        raise MultiExportError("only clone Project instances are supported")
    if (project.scan.get("content_size") != list(content_size)
            and project.scan.get("content_size") != tuple(content_size)):
        raise MultiExportError("all calibrated projects must share the input content size")
    size = project.scan.get("proj_size")
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(type(v) is not int for v in size)
            or not 2 <= size[0] <= 1920 or not 2 <= size[1] <= 1080
            or size[0] * size[1] > MAX_OUTPUT_PIXELS):
        raise MultiExportError("invalid bounded projector output dimensions")
    try:
        mesh = np.asarray(project.result["mesh"], dtype=np.float64)
        if mesh.ndim != 3 or mesh.shape[2] != 2 or min(mesh.shape[:2]) < 2:
            raise ValueError("unexpected mesh dimensions")
        mesh = np.where(np.isfinite(mesh), mesh, np.nan)
        if not np.any(np.isfinite(mesh).all(axis=2)):
            raise ValueError("mesh has no valid projector points")
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise MultiExportError(f"invalid calibrated mesh: {exc}") from exc
    return mesh, tuple(size)


def export_multi(projects, content_path, output_dir, *, gamma=2.2, color_balance_profiles=None):
    """Render 2..8 calibrated outputs with shared content-space overlap weights.

    The output folder must be new. Partial output on error has no manifest.
    Returned metadata is software evidence only, not physical calibration.
    """
    if not isinstance(projects, (list, tuple)) or not 2 <= len(projects) <= MAX_PROJECTORS:
        raise MultiExportError("provide between 2 and 8 calibrated projects")
    if type(gamma) not in (float, int) or not isfinite(gamma) or not 0.5 <= gamma <= 4.0:
        raise MultiExportError("blend gamma must be finite and between 0.5 and 4.0")
    profiles = (None if color_balance_profiles is None else
                color_balance.validate_profiles(color_balance_profiles, len(projects)))
    image = _validated_source(content_path)
    content_size = (image.shape[1], image.shape[0])
    prepared = [_validated_mesh(p, content_size) for p in projects]
    masks = [calib.coverage_mask(mesh, content_size) for mesh, _ in prepared]
    if any(not mask.any() for mask in masks):
        raise MultiExportError("one or more calibrated projectors have no content coverage")
    if len(projects) * content_size[0] * content_size[1] > 32_000_000:
        raise MultiExportError("projector count times content pixels exceeds CPU memory budget")
    # OpenCV distanceTransform returns near-FLT_MAX for a mask containing
    # only ones (no zero-distance reference), causing float32 sum overflow.
    # Supply a one-pixel zero border, then remove it after the existing blend
    # algorithm. This produces finite distance-to-edge weights for full masks.
    padded_masks = [np.pad(mask, 1, mode="constant", constant_values=False)
                    for mask in masks]
    padded_alphas, padded_linear = calib.edge_blend_weights(
        padded_masks, gamma=float(gamma))
    alphas = [a[1:-1, 1:-1].copy() for a in padded_alphas]
    linear_weights = [a[1:-1, 1:-1].copy() for a in padded_linear]
    covered_count = np.sum(np.stack(masks, axis=0), axis=0)
    covered = covered_count > 0
    # The existing distance-transform implementation returns zero right on
    # mask boundaries, even when a pixel has coverage. Divide those boundary
    # pixels equally across the covering projectors rather than leave a dark
    # seam or falsely report that their blend sum is normalized.
    total_weights = np.sum(np.stack(linear_weights, axis=0), axis=0)
    zero_weight = covered & (total_weights <= 1e-6)
    if zero_weight.any():
        count_safe = np.maximum(covered_count, 1)
        for i, mask in enumerate(masks):
            linear_weights[i][zero_weight] = (
                mask[zero_weight].astype(np.float32)
                / count_safe[zero_weight].astype(np.float32))
        alphas = [np.power(weight, 1.0 / float(gamma)).astype(np.float32)
                  for weight in linear_weights]
        total_weights = np.sum(np.stack(linear_weights, axis=0), axis=0)
    if not np.allclose(total_weights[covered], 1.0, atol=1e-4):
        raise MultiExportError("overlap weights are not normalized")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for i, (project, (mesh, size), alpha, mask) in enumerate(
            zip(projects, prepared, alphas, masks), start=1):
        frame = render.render_projector(image, mesh, size, alpha=alpha)
        if profiles is not None:
            frame = color_balance.apply_preview(frame, profiles[i - 1])
        filename = f"projector_{i:02d}.png"
        path = output / filename
        if not cv2.imwrite(str(path), frame):
            raise MultiExportError(f"failed to write {filename}")
        records.append({
            "project_index": i,
            "project_name": str(project.name)[:120],
            "image_file": filename,
            "projector_size": list(size),
            "coverage_fraction": round(float(mask.mean()), 6),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })

    result = {
        "schema": "kmj.multi-projector.offline.v1",
        "software_preview_only": True,
        "hardware_acceptance": "NOT_VERIFIED",
        "content_size": list(content_size),
        "projectors": records,
        "blend_gamma": float(gamma),
        "overlap_fraction": round(float(np.mean(covered_count > 1)), 6),
        "uncovered_fraction": round(float(np.mean(~covered)), 6),
    }
    if profiles is not None:
        result["color_balance_preview"] = {
            "schema": color_balance.SCHEMA,
            "profiles": profiles,
            "hardware_photometric_acceptance": "NOT_VERIFIED",
        }
    (output / "manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result
