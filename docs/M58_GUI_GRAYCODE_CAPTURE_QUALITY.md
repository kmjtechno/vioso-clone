# M58 — Read-only Gray-code Capture Quality from Studio

The CLI already had the M25 bounded check_capture() algorithm for capture
manifests, Gray-code image integrity, camera contrast, decoded pixel
coverage and projector-axis span. M58 exposes this important step in the
Premium Dark GUI without needing a command line.

## Workflow

From the sidebar choose **Check Capture Quality**, or from Calibration
choose **Check captured Gray-code quality (offline)**.

Select an **existing** camera capture directory created by the clone, with
capture_manifest.json and its pNN/nNN grayscale PNG pairs. Set the bounded
contrast margin, minimum decoded-valid-pixel fraction and minimum projector
axis span. Optionally choose a camera ROI mask PNG or fisheye rectification
profile JSON **by basename within the same capture folder**.

After explicit consent, a background CPU-only worker reuses the strict M25
parser. The report includes total Gray-code pattern pairs, minimum reliable
pair fraction and decoded valid-pixel fraction. All data remain local.

**This check never powers either projector, starts a camera, creates images,
modifies the manifest, or updates the user's calibration project.** It
also never displays raw filesystem paths or native decoder errors in logs.

## Safety/limits

The M25 engine strictly bounds manifest/image size, PNG format/resolution,
decoded camera pixels and numerical gates. The GUI refuses symlink folders
and selected optional files; it reads only operator-selected files.
Failure is sanitized to CAPTURE_CHECK_REFUSED or CAPTURE_CHECK_FAILED.

Successful quality screening means captured data meet software thresholds.
It is not proof that the CP PLUS stream was a raw 1O fisheye image, that
a measured lens intrinsic solve is accurate, or that actual projectors
are aligned. No hardware acceptance is inferred.

## Verification

- Inert form until explicit read-only consent.
- Existing regular capture manifest required, no path traversal.
- Optional ROI and fisheye profile must be local basenames.
- Worker calls tested M25 check_capture(), renders only bounded metrics,
  and redacts native exceptions.
- Qt menu and sidebar wired to the existing behavior; no devices in tests.
- Exact-head Linux/Windows regressions and portable EXE startup required.

See [M25 specification](M25_CAPTURE_QUALITY.md) and
[hardware acceptance tracker](https://github.com/kmjtechno/vioso-clone/issues/67).
