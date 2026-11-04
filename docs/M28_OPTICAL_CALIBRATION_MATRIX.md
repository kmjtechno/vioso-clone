# Optical calibration feature mapping — clean-room VIOSO 7 research

**Evidence rule:** names and observed behavior are mapped to original, independently authored code. No vendor routines, protected assets, calibration LUTs, binaries or licensing logic are copied. A documentation feature does **not** imply implementation or hardware equivalence.

Official public documentation used for externally verifiable capability descriptions:
- [VIOSO 7 calibration overview](https://vioso.com/calibration-software/vioso7/)
- [Scanning modes and device choice](https://docs.vioso.com/calibration/scanning/device-selection)
- [Camera ROI masking](https://docs.vioso.com/calibration/scanning/camera-adjustment/camera-masking-region-of-interest)
- [Projector masking](https://docs.vioso.com/calibration/scanning/projector-masking)
- [Blending/global adjustments](https://docs.vioso.com/calibration/blending)
- [Black-level compensation methods](https://docs.vioso.com/calibration/blacklevel-compensation)
- [VIOSO 7 marker-based pose estimation](https://docs.vioso.com/calibration/content-mapping/3d-mapping/camera-pose-estimation-in-vioso-7)

| Optical capability | Independent clone implementation/evidence | Remaining acceptance |
| --- | --- | --- |
| Projector gray-code capture/decoding | M2/M8 capture and synthetic decoder; M25 read-only scan quality; **M28 camera ROI masking** | Measured camera/projector capture with fixed focus and repeatability |
| Camera field of view and mask | M28 strict black-included/white-excluded grayscale camera ROI applies to capture quality and project scan decode | Interactive mask editor; operator camera ROI confirmation |
| Projector pre-scan masks/cropping | **M29 opt-in grayscale projector-space mask applied to Gray-code patterns before projection**; M14 separately masks offline content overlap | GUI mask editor, operator optical overspill and dome cropping validation |
| Flat screen geometry/homography | M2 homography and warp mesh, synthetic | Real projected corners, reprojection RMS and lens distortion |
| Curved/dome/irregular geometry | M2 multi-plane fitting, content-space mesh | Lens-model/intrinsics-aware surface estimation and physical dome QA |
| Soft-edge blend | M14 normalized content-space overlap blending with gamma | Optical edge photometry and luminance/color gradients |
| Per-projector color | M27 opt-in bounded BGR gain/black subtraction on software frames | Real measured colorimetric matching and linear-light response |
| Black-level compensation | **Not implemented** as measured region-based black-level *uplift*; M27 encoded-black subtraction is not equivalent | Black-frame capture and region masks / measured projector response |
| 3D camera pose from markers | **M30 read-only OpenCV PnP RANSAC + LM with intrinsic/marker validation and reprojection gates** | Operator-mapped 3D markers, actual camera/lens data, projected physical alignment QA |
| Multi-projector sync | M15 opt-in still previews, no frame lock | GPU swap-chain, NDI/DirectX timing and synchronized output |
| Native VIOSO7 calibration format | Clone .sps only; read-only metadata probe | Owner-authorized native .sps sample + independent compatible spec and tests |

## M28 camera ROI mode

The clone accepts a **newly authored** or owner-supplied grayscale 8-bit non-interlaced `.png` of the same pixel dimensions as the recorded **camera frames**. Following the public camera mask semantics, **black (0) is the included ROI** and **white (255) is excluded**. Mixed gray/antialias and unsafe/symlink images are refused. This is not projector masking: it changes which camera pixels are included in scan analysis, not the projected light field.

Inspect an existing clone Gray-code capture without touching hardware or owner files:

    vclone capture-check E:/KMJ/Captures/run-001 --camera-mask E:/KMJ/Captures/run-001/camera-roi.png

For subsequent independent `Calibrate` use, add a single **basename** (not absolute/traversal path) into the clone JSON project `scan` object:

    "camera_mask": "camera-roi.png"

The optical ROI is applied before detecting valid camera-to-projector pixels and before the mesh is computed. `capture-check` reports a valid-pixel fraction relative to the **included camera ROI**, not the whole sensor, and records `camera_mask_applied` and `camera_roi_fraction`. Without a mask, the previous unmasked decoder/quality behavior stays unchanged.

## Source discrimination

Earlier project-scoped reverse-engineering notes `docs/re_notes_sps.md` and `docs/re_notes_sps_dll.md` on the owner P520 identify a proprietary request dispatcher and probable downstream serializer. They **do not** establish the native optical calibration payload. The XML project writer with an SPS path is a different artifact from the native settings serializer. Therefore never claim that these independent clone masks or XML resemble the native SPS payload.

Hardware acceptance requires actual measurements and voluntary local operator choice. Do not force physical projection, register native vendor DLLs, or inspect protected licensing.
