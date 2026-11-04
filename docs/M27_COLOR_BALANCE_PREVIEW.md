# M27 — Bounded offline projector color-balance preview

The clean-room clone supports optional **software-only** BGR channel gain and encoded black subtraction on each existing M14 blended/projector preview. This is a preview control, **not** VIOSO 7 hardware or projector photometric calibration.

Create a UTF-8 JSON file, e.g. `balance.json`:

```json
{
  "schema": "kmj.color-balance.preview.v1",
  "projectors": [
    {"gain_bgr": [1.00, 0.95, 1.08], "black_subtract_bgr": [4, 3, 2]},
    {"gain_bgr": [0.94, 1.00, 1.03], "black_subtract_bgr": [0, 0, 0]}
  ]
}
```

Then export using **existing valid clone-format calibrated JSON projects**, a regular content image and a **new output folder**:

```
vclone export-multi content.png ./new-color-preview p1.json p2.json --color-balance balance.json
```

Projector record order matches the supplied project list exactly; BGR channel order is OpenCV's Blue, Green, Red (not RGB). File profile requires 2–8 entries. Gains are finite in 0.25..2.0, subtract offsets in 0..64 (8-bit code values). The algorithm first renders each warped/blended uint8 frame, subtracts the per-channel encoded offset with zero clamp, applies channel gains, then clips/rounds into 0..255. Completely black pixels stay black; no unobserved area is illuminated. With no flag the existing multi-output algorithm is unchanged.

Output `manifest.json` records the exact normalized preview settings, schema and `hardware_photometric_acceptance=NOT_VERIFIED`. Existing destination folders are refused and untrusted/oversized/symlink/invalid profile files fail closed before export. No physical display or camera is opened.

**Limits:** This is a software image preview, not physically measured projector luminance, true colorimetry, linear-light blending, gamma response, black floor, optical edge blend, synchronized multi-projector output or native VIOSO 7 file parity. Use authorized measured input/reference samples and separately qualify live hardware before claiming acceptance.
