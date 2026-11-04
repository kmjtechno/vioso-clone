# M14 — Offline multi-projector overlap/blend PNG export

The clone can now generate **separate calibrated preview images** for 2–8 projector projects sharing one content image. Projector-to-content mesh warps are rendered with existing OpenCV CPU code. The existing `calib.edge_blend_weights` computes per-projector content-space overlap ramps; the exporter applies the gamma-encoded weights when creating each PNG.

This is for offline planning and inspection: **the frames are not simultaneously presented by physical devices**, and the numbers are not measured color/black-level correction or synchronized output.

## Usage

Create 2–8 independently calibrated **clone-format JSON** projects. Each must specify the same `scan.content_size` as the source content PNG, with a valid `result.mesh` and bounded `scan.proj_size`. Then:

    vclone export-multi shared-content.png ./new-multi-output projector-a.json projector-b.json --gamma 2.2

Use a new, nonexistent output folder; the exporter never overwrites an existing directory. The folder contains `projector_01.png`, `projector_02.png`, and `manifest.json`. The manifest reports each image's SHA-256 digest, projector dimensions and fractional content coverage, overlap/uncovered fractions and `hardware_acceptance=NOT_VERIFIED`.

The blend weights represent clone-only content-space coverage of the calibrated meshes; gamma in 0.5..4.0. Multiple projects that cover the same region will receive normalized overlap ramps. Overlap is **not** validated against actual projector photometry, screen reflectance or optical alignment.

## Safety and validation

- 2–8 projectors; each output max 1920×1080; content max 4096×2160 and source file max 128 MiB.
- Content image must be a regular non-symlink file. Projects are clone-format JSON only.
- All meshes and size matching are validated before output creation; invalid/all-unobserved meshes fail closed.
- Partial write errors leave diagnostic PNGs but **no successful manifest**.
- No camera or projector is opened. Tested with synthetic overlapping meshes, normalized blend, output digests, invalid inputs and CLI invocation on Windows/Linux.
- Native VIOSO 7 .sps, synchronized GPU delivery, edge photometry and physical P520 multi-projector acceptance remain **NOT VERIFIED**.
