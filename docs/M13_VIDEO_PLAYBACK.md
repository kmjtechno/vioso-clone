# M13 — Experimental calibrated local video playback

The clone now has a bounded, opt-in **single-projector** local video preview. It uses OpenCV to decode ordinary local video files and the independent clone's CPU warp mesh to render each frame on a selected fullscreen display.

This is not a synchronized GPU/DirectX playback engine, multi-projector genlock, NDI or native VIOSO7 video output. Audio is not supported.

## Use

Install the optional GUI and an OpenCV build with window support. Generate a calibrated **clone-format JSON** project with `scan.proj_size` and `result.mesh` first.

Verify the projector's desktop position in the operating system's extended desktop display settings. Then:

    vclone present-video project.json local-video.mp4 --projector-x 1920 --projector-y 0 --fps 24 --seconds 10 --confirm-display

`1920,0` is an example, **not autodetected**. Escape stops playback. The command runs at most 30 seconds, at most 30 requested frames per second, with a maximum projector frame size of 1920x1080. Input files must be regular local MP4/MOV/AVI/MKV/WEBM files under 4 GiB; network URLs and symlinks are refused. A success receipt says only that synthetic/decoded frames were displayed, not that camera/projector performance was accepted.

The CPU renderer recomputes the warp for each frame. Requested FPS is an upper pacing target, **not** a guarantee: slow CPU rendering can lower actual frame rate; OpenCV window timing is not synchronized with projector refresh. Video files can fail to decode if the host's OpenCV codec build lacks the codec.

## Validation

- Synthetic generated frames exercise identity mapping and size/format gates without hardware.
- Fake OpenCV VideoCapture and fullscreen window tests exercise cleanup, Escape, early failure, user confirmation and CLI integration.
- GitHub Actions Linux/Windows Python 3.13 focused and full suites are the source-level acceptance gate.
- Physical P520 projector acceptance remains NOT VERIFIED; no original VIOSO binaries/files or license mechanisms are involved.

This is a functional increment toward playback parity, not a claim of full VIOSO 7 compatibility.
