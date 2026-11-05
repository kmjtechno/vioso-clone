# M61 — Manual warp mesh refinement in Calibration Studio

The independent clone already computes a measured Gray-code warp mesh, but
the old "Edit" command only accepted numeric offsets stored manually in
project JSON. M61 makes actual mesh-node correction accessible to operators
through a visual wireframe editor in the professional dark Studio.

## Workflow (offline, no device operations)

1. Complete a calibrated clone project using real Gray-code capture and
   independently measured camera-to-content corners.
2. Open **Edit Warp Mesh** in the Studio sidebar (or Calibration menu).
   The software reads the current in-memory calibrated mesh only.
3. Select a cyan observed control point on the wireframe; missing
   or unobserved nodes are not editable.
4. Enter relative content-space X and Y adjustments. Each node may move
   at most 64 pixels per axis relative to its original position in this
   editor session. Click **Apply node adjustment** to update the detached
   preview mesh. Repeat for different nodes.
5. **Cancel — discard changes** leaves the project untouched. **Save reviewed
   mesh corrections** validates the entire proposed mesh against the existing
   topology and finite coordinates, re-rasterizes software coverage and
   commits in one in-memory project transaction. Only this Save marks the
   project dirty. Previous Export completion is invalidated.
6. Inspect the CPU warped content preview. Save your clone JSON project
   through File → Save only after validating the corrections. You may then
   use M59 single or M60 multi-projector still presentation *with explicit
   independent display consent*.

No real-time camera feed, projector power, screen projection, network,
captured image changes, video recording or automatic project-file write
occurs when editing a mesh. This is **manual warp geometry correction**,
not full VIOSO 7 geometry software or certified optical calibration.

## Honest limits

The editor adjusts an existing calibrated mesh; it does not manufacture
a camera intrinsic solve, infer 3D dome geometry, recover missing nodes,
repair a folded mesh automatically or assess a physical blend seam.
Native VIOSO 7 SPS interchange, GPU-synchronized multi-projector video,
NDI, hardware color calibration and signed commercial installers remain
separate feature/evidence tracks. Real acceptance requires on-P520
hardware tests in [issue #67](https://github.com/kmjtechno/vioso-clone/issues/67).

Tests use only synthetic clone meshes, PySide6 offscreen scenes and
CPU-only coverage recomputation. No paid providers or proprietary code.
