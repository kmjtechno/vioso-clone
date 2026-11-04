# M37 — Two-projector seam and overlap preflight (offline)

This feature is designed for the owner's Windows P520 with one webcam, one CP PLUS fisheye IP camera and **two physically connected projectors that are still OFF**. It checks whether two **already calibrated, clone-format** optical meshes cover a common content canvas, have a useful shared seam and are not just duplicated/mirrored geometries.

## Exact read-only invocation

```text
vclone two-projector-check E:/KMJ/Calibration/left-projector.json E:/KMJ/Calibration/right-projector.json
```

It never opens a camera stream, projector window, network source, USB device or output file. It reads only the two existing project JSONs and rasterizes their valid content-space mesh polygons in RAM.

The output is a JSON receipt with:

- Per-projector content coverage fractions, content bounding rectangles and projector sizes.
- Two-projector overlap measured as a **fraction of the smaller projector's covered content** (the best interpretation for seam overlap), plus overlap as a fraction of total content.
- Combined union coverage and uncovered fraction.
- Explicit software gate, always with `hardware_optical_acceptance=NOT_VERIFIED`, `projection_synchronization=NOT_VERIFIED`, `projector_identity_mapping=NOT_VERIFIED` and `native_vioso_sps_compatible=false`.

Default software acceptance requires at least **5%** and at most **85%** overlap of the smaller content footprint and at least **50%** content union coverage. These are **initial software preflight screening thresholds**, not manufacturer specifications or proof of optimal physical blend width. They can be changed for a confirmed geometry:

```text
vclone two-projector-check left.json right.json --min-overlap 0.03 --max-overlap 0.90 --min-union-coverage 0.75
```

A disjoint non-blending layout is reported `BLOCKED_INSUFFICIENT_SEAM_OVERLAP`, nearly identical projectors `BLOCKED_EXCESSIVE_OR_DUPLICATE_OVERLAP`, and a small content union `BLOCKED_LOW_CONTENT_COVERAGE`. Valid ranges, mesh shapes, content coordinate system and memory limits are checked before rasterization. This action has **no file writes**; even a blocked seam returns a structured report and a nonzero exit code.

## Important hardware interpretation

- This requires two genuinely calibrated projects. The source test uses synthetic meshes; synthetic PASS does not prove the camera, projector output, lens distortion, homography or mounting geometry.
- Calibrate the two projectors **sequentially** with Gray-code patterns. Do not project calibration patterns on both simultaneously. With the CP PLUS raw fisheye camera, first fit its own native-resolution M32 lens model, then apply the same M35 rectification consistently to both captures.
- On the owner's current PC both projectors may remain **OFF** during software work. Before a real scan the operator will be asked **once** to power both ON, confirm Windows extended-desktop mappings, distinguish left vs right projectors and physically verify the camera field of view.
- Overlap alone is not blend-quality acceptance. Real seam brightness, black floor, gamma, color, frame sync and multi-output photometric tests remain separate.
- Full VIOSO 7 proprietary compatibility, native `.sps` interoperability and commercial readiness are not claimed. No extra paid provider required.
