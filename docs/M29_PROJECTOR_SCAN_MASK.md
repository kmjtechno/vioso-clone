# M29 — Projector-side optical masking during Gray-code scan

This independently authored clone uses a **projector-space grayscale mask** to limit overspill during an opt-in physical camera/projector Gray-code capture. The VIOSO 7 public documentation describes projector masks for excluding off-screen overspill and cropping unwanted blend zones:
https://docs.vioso.com/calibration/scanning/projector-masking

This is NOT a copied vendor XML mask file and NOT the same as M28 camera ROI masking.

## Inputs and semantics

- Mask is an existing **regular, non-symlink, 8-bit grayscale, non-interlaced PNG** with dimensions exactly matching the selected projector output resolution (maximum 1920x1080).
- In **projector mask** pixels, **black (0) blocks projection**, **white (255) permits full pattern**, gray values 1..254 permit corresponding intermediate intensity for feathering.
- In contrast, the **camera ROI** mask used by M28 has **black (0) included in scanning** and **white (255) excluded**. Do not reuse the two mask types without consciously inverting the semantics.
- Entirely black/undersized/corrupt/mis-sized/unsafe masks are refused before any camera is opened. Mask file is never modified.

## Physical use (requires operator confirmation)

After verifying the projector output desktop coordinates and camera index locally:

```
vclone capture-graycode --width 1280 --height 800 --camera 0 \
  --projector-x 1920 --projector-y 0 \
  --out E:/KMJ/Captures/new-masked-session \
  --projector-mask E:/KMJ/Masks/projector-01.png \
  --confirm-display
```

**The coordinates are examples, not an autodetected monitor assignment.** Confirm the actual extended-desktop projector location first. No physical device is started without the original `--confirm-display` operator gate.

Each projected Gray-code frame and its inverse is multiplied by the mask; blacked-out areas remain dark. Saved camera frames remain unmodified. The normal capture manifest includes extra `projector_mask_applied` and a SHA-256 digest of mask pixel bytes for audit when a mask was selected. Unmasked capture behavior and manifest remain unchanged. Failed captures still do not produce successful manifests.

This feature does not automatically measure projector overspill or create masks. The operator supplies a consciously constructed mask. No real P520 hardware acceptance, native VIOSO 7 SPS, calibrated optical blend, realtime NDI or synchronized GPU output is claimed.
