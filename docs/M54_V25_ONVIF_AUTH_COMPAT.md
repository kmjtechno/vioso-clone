# M54 — KMJ Calibration Pro V2.5 CP PLUS ONVIF compatibility

The owner's older `KMJ Calibration Pro V2.5` executable was reported to
connect the same CP PLUS camera without prompting again for ID/password.

Previously retained **sanitized diagnostic logs**, not original V2.5
source-code or any credential files, establish:

- The old application used `CPPLUS_CRED_SOURCE=secure_profile` and never
  logged the password; the lack of a login prompt did **not** prove the
  camera was anonymous.
- Its initial ONVIF UsernameToken PasswordDigest attempt failed, then
  a UsernameToken **PasswordText + Nonce + Created** attempt over HTTPS
  succeeded.
- The device returned 27 Media1 entries, including a MainStream token
  `MediaProfile00000`; an RTSP stream URI could be retrieved using that
  token even though older camera profile metadata showed no usable width
  or height.

These are hardware-history observations only, **not current physical
connectivity or credentials verified in VIOSO Clone**.

## What M54 reimplements

1. Existing ONVIF WSSE PasswordDigest, HTTP Digest and no-password
   anonymous modes remain unchanged.
2. An explicitly owner-selected private RFC1918 camera with BOTH credentials
   supplied and a **certificate-verified HTTPS** control endpoint uses
   PasswordDigest first. Only on HTTP 401/403 or a narrowly recognized
   SOAP `NotAuthorized/FailedAuthentication/InvalidSecurity` fault does it
   retry once with the same owner credential as a WSSE
   `#PasswordText` accompanied by fresh `Nonce` and UTC `Created`.
3. **Never** send PasswordText over HTTP, on SSL validation errors,
   redirects, unknown host responses, malformed XML, generic HTTP 500, or
   anonymous/partially supplied accounts. There is no default-password
   guessing, vendor secret extraction, or automatic disabling of TLS trust.
4. Increase bounded ONVIF profile parsing from 16 to 64 because the old
   CP PLUS camera returned 27 entries. Preserve legitimate profile tokens
   even if VideoEncoderConfiguration Resolution is absent or zero.
5. Prefer unique largest square with actual dimensions as before; only
   when no square is advertised accept the one known legacy MainStream
   token `MediaProfile00000` as a connection-only candidate. The resulting
   stream can be visually tested, but its dimensions and lens/raw-1O
   geometry are **NOT VERIFIED** merely by choosing the token.
6. Camera credentials and URI are never added to the project, GitHub,
   screenshot, camera probe report or user-facing exception. Any cache
   migration must be performed locally by the owner with explicit
   permissions and a verified secure-profile storage format.

## What is deliberately NOT done

The V2.5 program lives at an owner-specified local Windows path outside the
currently granted CodeBridge project root. The GitHub `kmj-calibration-pro`
main branch contains a newer C++ v4 scaffold, **not** the exact local V2.5
ONVIF login source. The older program's saved credential store was not
inspected, copied, decrypted or uploaded. This change ports only independently
testable behavior grounded in sanitized historical logs and OASIS/ONVIF
requirements.

HTTPS camera firmware may use a self-signed or private CA certificate. The
application still requires OS-verifiable TLS trust; use owner-controlled
Windows trust settings for any authorized certificate, never a trust-all
exception. Real camera credentials remain in the legacy owner's secure
profile until locally authorized access exists.

## Physical qualification required

1. On P520, launch the new verified Windows alpha after release.
2. First run **Connect ONVIF Camera > Auto Detect** with login blank.
3. If anonymous media access is denied, provide the owner's already-authorized
   ONVIF account locally. Select HTTPS only if the camera presents a trusted
   certificate. No account/password is needed in this chat.
4. Check camera-only frame test and original fisheye preview while both
   projectors remain OFF. This is not a calibration acceptance.
5. Only after camera frames and intrinsics are verified, the owner can
   physically power on projectors for the optical mapping/edge blend gate.

Synthetic regression exercises both authentication modes, exact retry
conditions, 27-profile Media1 parsing and non-disclosure. CI cannot
establish V2.5 profile migration, current CP PLUS firmware compatibility,
raw 1O geometry, dual projector blend, signed installation or proprietary
VIOSO 7 SPS parity.

Reference specifications:
- https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-UsernameTokenProfile-v1.1.1-os.html
- https://www.onvif.org/wp-content/uploads/2016/12/ONVIF_WG-APG-Application_Programmers_Guide-1.pdf
