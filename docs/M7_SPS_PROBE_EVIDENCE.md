# M7 — Read-only SPS header evidence and limitations

## Scope

Run `python -m vclone.sps_probe <owner-authorized-file.sps>` to inspect at most 64 KiB of a regular, non-symlink file. The inspector reports declared XML version/build, `binOffset`, `binSize`, `binSizeRaw`, compression flag and file size. It **never reads, decompresses or interprets the payload**; no project is loaded or written, and no original VIOSO binaries are executed.

The output always states `evidence_scope: XML_METADATA_ONLY`, `payload_verified: false`, and `native_compatibility: NOT_VERIFIED`. A matching header does not prove that the clone can load native VIOSO 7 projects. The 64 KiB / 64 MiB limits are clone safety policy, **not** native file format limits.

## Evidence ledger

| Claim | Evidence | Confidence | Limitation |
|---|---|---|---|
| Independent clone writes XML root VIOSO, File and data nodes | M5 `vclone/sps.py` and `tests/test_m5_sps.py` | VERIFIED for clone only | Not a native-format claim |
| 20-digit binOffset identifies the end of clone XML header | M5 writer and M6 loader | VERIFIED for clone only | Native interpretation unknown |
| binSize, binSizeRaw, bCompressed appear in clone header | Clone source and M6 negative tests | VERIFIED for clone only | Native payload unknown |
| Installed VIOSO software may use similar elements | Prior static research referenced by `SPEC.md` and PRs #17/#25 | REPORTED, not independently re-attested in this PR | No authorized native .sps sample or binary SHA accessible through GitHub alone |
| New metadata probe avoids reading payload | `vclone/sps_probe.py` and `tests/test_m7_sps_probe.py` | VERIFIED by isolated synthetic unit tests | Native/hardware not tested |

## Security and compatibility gates

- Reject XML DTD/ENTITY, invalid declarations, malformed XML, duplicate structural nodes, wrong binOffset width, oversized or negative size attributes, invalid compression flag, XML boundary mismatches, truncated/trailing payload length, non-regular/symlink input and oversized files.
- For a native sample, obtain explicit owner authorization. Record permitted sample SHA-256 locally, redact metadata as appropriate, and compare only allowed observations. Never commit native binary projects, DLLs, license/protector files or vendor decompiled source.
- **Pending:** actual native VIOSO 7 .sps fixtures, native import/export interoperability, physical projector QA, and P520 Windows end-to-end GUI acceptance.

## Owner-side tests

```powershell
python -m vclone.sps_probe 'E:\path\to\owner-authorized.sps'
python -m pytest tests/test_m7_sps_probe.py -q
python -m pytest -q
```

A successful metadata probe is **not** a native compatibility or projector calibration certification.
