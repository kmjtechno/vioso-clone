# M57 — Offline multi-projector blend export from Calibration Studio

M14 already supports bounded CPU rendering of 2–8 independent, calibrated
clone projects with normalized content-space overlap weights, per-projector
PNG assets and a checksum manifest. M57 makes this real feature accessible
in the professional Windows GUI rather than requiring the CLI.

## Operator workflow

Open Calibration Studio and choose **Offline Blend Export** in the sidebar
(or **Calibration > Export offline multi-projector blend**).

1. Select **2–8 DISTINCT existing clone project JSON files** with
   independently generated valid warp meshes and matching content sizes.
2. Choose a local content image (PNG, JPEG, BMP) and set the blend gamma
   (0.50–4.00; default 2.20).
3. Select an **existing parent** and specify an entirely **NEW output
   directory**. Existing folders, symlinks and duplicate project files
   are rejected; no owner data is overwritten.
4. Tick the explicit offline-render consent checkbox and click OK.
5. A background worker calls the existing M14 export engine and writes
   projector_01.png, projector_02.png, etc., plus a manifest.json with
   checksums and software overlap/uncovered metrics. No projector or
   camera hardware is accessed, no fullscreen window appears.
6. Review the rendered PNGs and M14 manifest offline. Do not mistake
   their successful generation for physical two-projector seam/blend
   acceptance or synchronized video output.

The GUI reports only the projector count and software-only completion
state. Native Python/OpenCV exception strings, raw project paths, camera
accounts and image content are never added to the session activity log.

## Regression coverage

- Qt form is inert until 2–8 distinct project paths, local content and
  NEW output folder are selected and the owner checks consent.
- Existing output folder is refused rather than replaced.
- Worker delegates to the already-tested M14 CPU export engine and
  passes bounded gamma without making projector calls.
- Untrusted backend errors are reduced to a fixed generic code;
  completed output is clearly **NOT VERIFIED** against real optics.
- GUI action is wired to the real method in the sidebar and
  Calibration menu; no false device status is introduced.
- Full Linux/Windows source regressions, offscreen GUI and actual frozen
  Windows EXE/ZIP startup are needed before release.

## Still pending separately

Actual CP PLUS ONVIF frames, webcam intrinsic fit, two projector optical
mapping, physical seam/blacklevel/color, and native VIOSO 7 interchange
are not established by offline PNG generation.

See [M14 offline CPU blend details](M14_MULTI_PROJECTOR_OFFLINE.md)
and [physical gates](https://github.com/kmjtechno/vioso-clone/issues/67).
