# M31 — Read-only optical black-level camera-frame analysis

VIOSO's public documentation describes projector residual light, overlap buildup and region-based **black-level uplift**. Source: https://docs.vioso.com/calibration/blacklevel-compensation and https://docs.vioso.com/preparation/projectors/blacklevel-explained

The clone's M31 tool implements an independently designed **measurement diagnostic**, not VIOSO's compensation algorithm. It reads owner-measured 8-bit grayscale camera frames taken with **fixed camera exposure/gain**: one ambient reference and a separate black frame per projector. Projector coverage masks are defined in the same **camera sensor coordinate system**, not native projector-space calibration maps.

Create a JSON manifest (example for two projectors):

```json
{
  "schema": "kmj.blacklevel.frames.v1",
  "acquisition_mode": "single_projector_black_vs_ambient",
  "camera_size": [1280, 720],
  "ambient": "ambient.png",
  "projectors": [
    {"name": "P1", "black_frame": "P1-black.png", "coverage_mask": "P1-coverage.png"},
    {"name": "P2", "black_frame": "P2-black.png", "coverage_mask": "P2-coverage.png"}
  ]
}
```

All image names are simple basenames in the manifest's folder. PNG must be 8-bit noninterlaced grayscale, exact camera dimensions, regular non-symlink, and bounded in size. Projector **coverage masks are white=covered, black=not covered**. Optional `camera_roi` is a separate **M28 camera ROI** PNG: black=included and white=excluded. These are *not* M29 projector-output masks.

Run read-only:

    vclone blacklevel-check E:/KMJ/Captures/blacklevel-session/blacklevel.json

The JSON result contains camera ambient median, individual projector black-minus-ambient median and p95 values, overlap fraction and a diagnostic *additive* estimate of overlap and nonoverlap 95th-percentile encoded brightness.

**Important limits**

- Values are **8-bit camera image code levels**, not certified cd/m², spectral/colorimetry, projector transfer functions or optical calibration LUTs.
- It cannot verify that ambient and black frames were captured with unchanged exposure, geometry, lamp states, or all other projectors disabled. The operator must ensure that manually.
- The additive overlap estimate is a useful screening approximation, not a physically modeled camera/projector response.
- No output texture, mask, projector-control command, black-level uplift or owner-file mutation is produced. Region-based calibrated uplift is **still unimplemented** pending real measured reference data and physical acceptance.
- It does not read original VIOSO 7 vendor SPS or proprietary binaries, does not claim optical hardware acceptance, and has zero required paid external services.
