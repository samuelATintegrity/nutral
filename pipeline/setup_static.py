"""
pipeline/setup_static.py — one-time setup to pre-generate the static closing MP3.

Run locally once after setting up your environment:

    python -m pipeline.setup_static

This creates the `closing.mp3` in the `segments` bucket, reused forever in every
brief. Re-running just overwrites it (idempotent).
"""

from __future__ import annotations

from dotenv import load_dotenv

from pipeline import audio, db, storage

CLOSING_TEXT = "That's your brief. Have a wonderful day."


def main() -> int:
    load_dotenv()
    print("[setup] Generating static closing MP3…")

    mp3_bytes = audio.generate_mp3_bytes(CLOSING_TEXT, use_ssml=False)
    print(f"[setup] Generated {len(mp3_bytes)} bytes")

    # Upload directly under the segments bucket with a stable key.
    sb = db.admin_client()
    sb.storage.from_(storage.BUCKET_SEGMENTS).upload(
        path="closing.mp3",
        file=mp3_bytes,
        file_options={"content-type": "audio/mpeg", "upsert": "true"},
    )
    print(f"[setup] Uploaded to {storage.BUCKET_SEGMENTS}/closing.mp3")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
