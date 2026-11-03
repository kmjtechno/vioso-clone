# RE notes: SPeASY64.dll (.sps save/load), read-only

Clean-room notes, own words. Static analysis only, nothing executed. No licensing, no copying.
Scope: the `SPBehaviourRequest` handler (request code 0xb save, 0xa load) and what sits behind it.
Tags: **VERIFIED** = decompiled or observed in the string inventory. **INFERRED** = not proven by a code path.
Produced in the owner's local Claude Code session; addresses were not independently re-checked.

Target: `SPeASY64.dll`, PE x86_64, 22,390,784 bytes, SHA-256
`bfb99d89c6a9b1d420779a84e5c55194e5297f46e9590a8a5a178679e5c92124`.

## 1. Request wrapper

- **VERIFIED:** `SPBehaviourRequest` @ `0x180669bd0`, signature `int f(request*, int* err, int, ulong)`.
  It proceeds only if the request's second dword is 0x11 and a filename pointer at +0x20 is non-null;
  otherwise it forwards.
- **VERIFIED:** switch on the first dword: 0xa opens the file for binary read (load), 0xb for binary
  write (save); 9 opens for write, 8 does not open; 0xc opens for read; 0xd to 0x11 are forwarded;
  anything else sets error 0xd and returns -1. An open failure sets error 0x48 and returns -1.
- **VERIFIED:** on success it stores the FILE handle in the request, calls the dispatcher
  `FUN_1802c83e0`, then closes the handle (likely fclose) and restores the filename pointer.
- **VERIFIED:** `FUN_1802c83e0` is only a dispatcher/queue (finds an "APP" object, sends message 0x73,
  waits in a message pump). No XML, compression or version logic. The real serializer is downstream
  of message 0x73, not in the wrapper.

## 2. XML shape (what is known)

- **VERIFIED:** the DLL builds its XML through the MSXML DOM (COM), not printf. Helper
  `FUN_180454410` creates a child node `data` with attributes `binOffset`, `binSize`, `binSizeRaw`
  and `bCompressed`. So binary blobs are referenced from the XML by offset, stored size, raw size and
  a per-blob compressed flag. **INFERRED:** the blobs live in a sidecar or tail section; `binSize` vs
  `binSizeRaw` are stored vs raw size.
- **VERIFIED (header templates):** VIOSO XML files use root `<VIOSO>` with a child
  `<File version="x.y.z" build="N"/>`. Templates seen: version `1.0.0` in several, ISO-8859-1 and
  UTF-8 variants, one with build `6070`, and one with a `%s` encoding parameter. The sibling element
  `<SPeASY>` appears under the root in some templates.
- **VERIFIED:** one function writes a plain-text *task script* (not `.sps`) using such a header and
  `</VIOSO>`, uncompressed. So the header convention is shared across VIOSO XML files.
- **INFERRED:** the `.sps` itself uses the same root and `File` header; not yet tied to the 0xb save path.
- **VERIFIED:** the DLL exports `SPGetSPSFileVersionStringA/W`, so a `.sps` carries a version string.
  Its source is not found.

## 3. Compression

- **VERIFIED:** setting names `bUseCompressedXmlFiles`, `iCompressLevel`, `bCompressed`; exports
  `SPSetDefaultXmlFileSaveParam_Compressed` and `_CompressLevel`. zlib `deflate 1.3.1` and minizip
  `zip/unzip 1.01` are statically linked.
- **INFERRED:** compression is optional deflate. Whether the container is raw zlib or a zip archive is
  unconfirmed. Where the flag is read (the settings handler `FUN_1806530d0`, 81 KB) is verified only
  by location, not by meaning.

## 4. Default save names (VERIFIED from strings and two small functions)

`Calib_%.2i%.2i%.2i.sps`, `SPSet_XML_YYMMDD_hhmmss_mmm.sps`, `SPSuperSet.sps`, `Preset%i.sps`,
`Settings%i.sps`, `Scan.sps`, `Final.sps`. The two small functions only build these default names
and default folders (for example `Calibration\`); they do not serialize.

## 5. Not established

The `.sps` element and attribute layout, the version value actually written, the compression
container, and the blob layout. Candidate XML writers that call the `data` helper (not yet read):
`0x18037fcb0`, `0x18047cf90`, `0x1804890d0`, `0x1805073c0`, `0x1805261c0`. Next steps: read those
writers, search for the creation of the `VIOSO` element, and find the flag use sites for compression.
