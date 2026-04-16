"""
pipeline/stitch.py — concatenate multiple MP3 byte-streams into one.

Uses pydub + static-ffmpeg (same stack as Artificial Tribune's dialogue mode).
Lazy imports so modules that don't need stitching don't pull in ffmpeg.
"""

from __future__ import annotations

import io
import os
import tempfile


def _configure_pydub():
    """Point pydub at the static-ffmpeg binaries + add them to PATH.

    pydub looks up ffprobe via PATH for mediainfo_json(), so setting the
    attrs alone isn't enough — we also have to extend PATH in-process.
    """
    from pydub import AudioSegment
    import static_ffmpeg

    ffmpeg_path, ffprobe_path = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
    AudioSegment.converter = ffmpeg_path
    AudioSegment.ffmpeg = ffmpeg_path
    AudioSegment.ffprobe = ffprobe_path

    ffmpeg_dir = os.path.dirname(ffmpeg_path)
    if ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    return AudioSegment


def concat_mp3s(mp3_blobs: list[bytes], silence_ms: int = 400) -> bytes:
    """
    Concatenate a list of MP3 byte-strings into one MP3 with `silence_ms`
    of silence between each segment.

    Returns the combined MP3 as bytes.
    """
    if not mp3_blobs:
        raise ValueError("concat_mp3s requires at least one input blob")
    if len(mp3_blobs) == 1:
        return mp3_blobs[0]

    AudioSegment = _configure_pydub()
    silence = AudioSegment.silent(duration=silence_ms)

    combined = AudioSegment.empty()

    # pydub.AudioSegment.from_mp3 wants a file-like object or path. Write each
    # blob to a temp file so ffprobe can read it (it shells out via subprocess
    # and can't read from an in-memory BytesIO reliably on Windows).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        for i, blob in enumerate(mp3_blobs):
            path = os.path.join(tmpdir, f"seg_{i:03d}.mp3")
            with open(path, "wb") as f:
                f.write(blob)
            clip = AudioSegment.from_mp3(path)
            if i > 0:
                combined += silence
            combined += clip

        out_path = os.path.join(tmpdir, "combined.mp3")
        combined.export(out_path, format="mp3")
        with open(out_path, "rb") as f:
            return f.read()
