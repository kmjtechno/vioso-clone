"""M55 safe UI camera failure explanations: codes only, never native errors.

All strings are constant, device-agnostic and contain no credentials,
addresses, serials, stream URLs or private profile paths.
"""
from __future__ import annotations

SCHEMA = "M55_CAMERA_PROBE_DIAGNOSTIC_V1"

FAILURE_HINTS = {
    "PROFILE_INVALID": (
        "Local profile validation",
        "Check the selected private camera address and ONVIF port. "
        "Both account fields must be provided or both left empty.",
    ),
    "ONVIF_AUTH_REJECTED": (
        "ONVIF authentication",
        "The camera rejected anonymous or supplied ONVIF login. The older "
        "V2.5 program may use a locally cached secure account; VIOSO Clone "
        "does not import those credentials automatically.",
    ),
    "ONVIF_CONTROL_UNREACHABLE_OR_TLS": (
        "ONVIF control connection or TLS",
        "Check that the camera is online, its advertised ONVIF service port "
        "is accessible, and any HTTPS certificate is trusted by Windows. "
        "Do not disable TLS validation.",
    ),
    "ONVIF_PROFILE_SELECTION_FAILED": (
        "ONVIF video profile selection",
        "Camera profiles did not identify one suitable stream. If you know "
        "the exact tested raw fisheye profile token, select it locally. "
        "Do not assume the first profile is a calibrated fisheye.",
    ),
    "ONVIF_STREAM_URI_UNAVAILABLE": (
        "ONVIF RTSP stream URI",
        "The selected media profile did not provide a usable RTSP URI. "
        "Check the camera's enabled video-stream profile locally.",
    ),
    "ONVIF_NEGOTIATION_FAILED": (
        "ONVIF media negotiation",
        "The device rejected or returned an unexpected ONVIF response. "
        "Confirm camera protocol compatibility and its ONVIF service settings.",
    ),
    "RTSP_DECODER_OPEN_FAILED": (
        "RTSP video stream or decoder",
        "ONVIF resolved the stream, but the local FFmpeg decoder could not "
        "open it. Check live RTSP permissions, supported codec and network.",
    ),
    "RTSP_TIMEOUT_UNAVAILABLE": (
        "RTSP timeout-capable capture backend",
        "The local OpenCV/FFmpeg build does not support required bounded "
        "network timeouts; do not bypass this safety requirement.",
    ),
    "CAMERA_WARMUP_FAILED": (
        "Camera frame warmup",
        "The video stream opened but could not deliver the warmup frame. "
        "Check camera stream format, stability and network locally.",
    ),
    "CAMERA_FRAME_READ_FAILED": (
        "Camera frame acquisition",
        "The camera stream opened, but six bounded frames could not be "
        "read. Check RTSP codec support and streaming stability.",
    ),
    "CAMERA_FRAME_FORMAT_INVALID": (
        "Video frame dimensions or format",
        "Frames were returned but dimensions, format or pixel budget were "
        "outside the accepted calibration range.",
    ),
    "CAMERA_PROBE_FAILED": (
        "Camera preflight (unclassified)",
        "The camera-only check failed safely before hardware acceptance. "
        "Retry on the verified latest build; check the local camera settings.",
    ),
}

def safe_failure(code):
    """Return a fixed tuple even for attacker-controlled exception messages."""
    if not isinstance(code, str) or code not in FAILURE_HINTS:
        code = "CAMERA_PROBE_FAILED"
    stage, guidance = FAILURE_HINTS[code]
    return code, stage, guidance
