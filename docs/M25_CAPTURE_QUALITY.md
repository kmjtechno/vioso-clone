# M25 — Read-only Gray-code capture quality gate

This independently implemented clone now has a software capture-screening command. It checks an existing capture folder *before* its frames are used for calibration:

    vclone capture-check E:/KMJ/Captures/run-001

No physical device is accessed. The command opens no camera, projector or window and does not mutate any input project, image or manifest.

## Checks

- Exact clone capture manifest v1, expected pNN/nNN image sequence and bounded projector and camera dimensions.
- No linked capture files, missing frames, oversized files, malformed/unexpected formats or unsupported PNGs. Each PNG must be non-interlaced 8-bit grayscale and match the recorded camera resolution.
- Pairwise absolute contrast greater than a configurable margin (default 20) and Gray-code decoding with bounded streaming memory.
- Decoded valid camera-pixel fraction (default >=0.30) and projector-coordinate span (each >=0.25 of its axis).
- Never claims calibrated optics, accurate color, black-level compensation, native VIOSO SPS, or synchronized multi-projector output.

An accepted folder prints machine-readable JSON with software_capture_quality=PASS, numeric quality evidence and hardware_acceptance=NOT_VERIFIED. A rejected folder exits 2 without writing a success manifest. Use a controlled capture for each projector and investigate rejected frames before calibrating.

You can tune screening thresholds if the projector occupies only part of a camera sensor:

    vclone capture-check E:/KMJ/Captures/run-001 --margin 20 --min-valid-fraction 0.15 --min-axis-span 0.20

A threshold reduction is not a waiver of physical geometry, optical contrast/black-level measurement or real-time projector QA. For formal acceptance, collect measurements with the actual P520 camera and projectors, verify mapping error, image uniformity, geometric error and display timing. Do not infer original VIOSO 7 vendor-file compatibility from these checks.
