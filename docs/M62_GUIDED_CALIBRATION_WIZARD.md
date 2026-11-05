# M62 — Guided Calibration Wizard (independent clean-room implementation)

Functional ten-stage software workflow built on working Qt/OpenCV calibration modules.
No proprietary VIOSO 7 code, licensed processing, images, UI assets or native project format copied.

## Owner workflow for a two-projector P520 rig

1. Project & Surface: create/open an isolated clone project; save Projector A to JSON.
2. Camera Setup: optional login ONVIF auto-detect/probe or USB/RTSP profile, six real frames with owner consent.
3. Projector Arrangement: read Windows Extended-desktop rectangles; owner maps physical projector identity.
4. Pattern Scan: capture real Gray-code patterns onto one confirmed projector at a time, or attach an existing session.
5. Scan Quality & Fisheye: strict M25 pattern decode, contrast and axis-span checks; attach measured matching fisheye profile from capture folder.
6. Surface Geometry: click TL,TR,BR,BL content corners; fisheye images are rectified in memory when measured lens profile exists.
7. Automatic Warp Solve: rerun M25; decode real Gray-code and compute mesh/coverage in detached CPU worker, commit only if source project and capture files remain unchanged.
8. Refine Geometry: edit warp control points visually and inspect CPU preview.
9. Two-Projector Compound: repeat A workflow for Projector B in separate saved JSON; compare geometries, render SHA-256-verified offline edge-blend stills.
10. Verify & Deploy: save clone JSON, preview, and optionally present timed stills after separate physical display consent.

## Masking

The physical Gray-code capture dialog supports a verified optional 8-bit grayscale projector PNG mask.
Black blocks projector pattern light, white passes full intensity and gray passes partial intensity.
The camera ROI mask and measured fisheye profile are scoped to the capture folder and used in CPU quality/warp checks.

## Safety and remaining gaps

Opening, navigating or closing the wizard never starts projector/camera hardware.
Actual camera probing and pattern projection require the existing explicit separate owner-authorized dialogs.
Back/Next navigation is exploratory, NOT hardware evidence. The quality and solve worker's PASS means software-screened images only.
The detached solver recomputes capture quality and checks project SHA-256 plus captured file metadata before updating the live project.
Unsaved dirty projects cannot be silently replaced by the New Project action.
Final output is independent clone JSON plus blend PNG; native VIOSO SPS is not guaranteed.

Full VIOSO 7 parity remains NOT VERIFIED: CP PLUS hardware, measured lens/surface quality, optical two-projector seam,
advanced curved/3D/dome methods, automatic black-level and color matching, genlocked GPU/NDI video, native SPS and Windows signing.
Projectors remain OFF until operator authorizes physical QA. See GitHub issue #67.

## Test gates

Real M25 and Gray-code decode on synthetic camera/projector images, forced low contrast, symlinks, changed PNG files,
stale corner coordinate spaces, project integrity and GUI no-hardware smoke are exercised on Windows/Linux CI.
Zero additional paid service dependencies and no changes to the owner's dirty P520 local source checkout.