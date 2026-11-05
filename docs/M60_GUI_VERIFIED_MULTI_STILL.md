# M60 — Present two calibrated projector stills from the GUI

This extends the working M14 offline 2–8-projector edge-blend PNG export
and M15 checksum-verified dual display still output into Calibration Studio.
It removes the requirement to use CLI `present-multi` for owner test rigs.

## How to use (owner confirmation required)

1. Complete real geometric calibration for each projector and generate
   M14 **Offline Blend Export** in a completely NEW folder.
2. Verify that the output contains `manifest.json` plus `projector_01.png`,
   `projector_02.png` (and up to 8) with SHA-256 hashes.
3. Physically turn ON and identify each projector, use Windows **Extend**
   displays (not Mirror) and match desktop resolution to the generated PNG.
4. In Calibration Studio, click **Present Multi Still** in sidebar, or choose
   **Calibration → Present verified multi-projector blend (confirmed)**.
5. Choose the existing verified output folder. Studio reads and checks the
   manifest and all PNGs but does NOT open projector windows yet.
6. Map every PNG to one different secondary Extended desktop rectangle. The
   primary screen, mirrored rectangles, duplicate screens and wrong-size
   outputs cannot be selected.
7. Select a duration of 1–10 seconds and tick the explicit opt-in checkbox.
   Read the independent final dialog; click **Yes** only if both physical
   projectors are ON and correctly mapped. No is the default.
8. The existing M15 engine revalidates every file's SHA-256, then opens one
   fullscreen still window per selected projector for the bounded interval.
   Escape ends the preview. It never auto-detects projector identity,
   changes monitor settings, turns on hardware or opens a camera.

## What this means

It is actual simultaneous **window presentation of distinct CPU-warped
and blended still images**. This is not frame-locked or time-synchronized
video; OpenCV windows are opened sequentially, with no swap-chain sync.
Synthetic CI does not measure projector focus, geometric alignment,
black-floor, exposure, color balance or the physical seam. Optical acceptance
remains NOT_VERIFIED until observed on the owner's real two-projector rig.

The feature does not implement proprietary VIOSO 7 .sps, GPU rendering,
NDI transport, genlock, 3D/dome calibration, real-time multi-projector
video or signed Windows distribution. Those are separate engineering tracks
listed in [issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).
No paid services or vendor-protected code are used.
