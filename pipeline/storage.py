"""
pipeline/storage.py — Supabase Storage uploads + signed URLs.

Three buckets (create in the dashboard, all private):
  - segments  — path: {date}/{category}.mp3
  - openings  — path: {user_id}/{date}.mp3
  - briefs    — path: {user_id}/{date}.mp3  (final stitched audio)

All buckets are private. The browser reads audio via short-lived signed URLs
generated server-side when an email is built or a /listen page is rendered.
"""

from __future__ import annotations

from datetime import date as date_cls

from pipeline.db import admin_client


# ---------------------------------------------------------------------------
# Bucket + path helpers
# ---------------------------------------------------------------------------

BUCKET_SEGMENTS = "segments"
BUCKET_OPENINGS = "openings"
BUCKET_BRIEFS = "briefs"

DEFAULT_SIGNED_URL_TTL = 60 * 60 * 24 * 30  # 30 days — emails + listen page


def segment_path(segment_date: date_cls, category: str) -> str:
    return f"{segment_date.isoformat()}/{category.upper()}.mp3"


def opening_path(user_id: str, brief_date: date_cls) -> str:
    return f"{user_id}/{brief_date.isoformat()}.mp3"


def brief_path(user_id: str, brief_date: date_cls) -> str:
    return f"{user_id}/{brief_date.isoformat()}.mp3"


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


def _upload(bucket: str, path: str, data: bytes) -> str:
    """Upload bytes to Supabase Storage, upserting if the path already exists."""
    sb = admin_client()
    sb.storage.from_(bucket).upload(
        path=path,
        file=data,
        file_options={"content-type": "audio/mpeg", "upsert": "true"},
    )
    return path


def upload_segment(segment_date: date_cls, category: str, mp3_bytes: bytes) -> str:
    return _upload(BUCKET_SEGMENTS, segment_path(segment_date, category), mp3_bytes)


def upload_opening(user_id: str, brief_date: date_cls, mp3_bytes: bytes) -> str:
    return _upload(BUCKET_OPENINGS, opening_path(user_id, brief_date), mp3_bytes)


def upload_brief(user_id: str, brief_date: date_cls, mp3_bytes: bytes) -> str:
    return _upload(BUCKET_BRIEFS, brief_path(user_id, brief_date), mp3_bytes)


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


def download(bucket: str, path: str) -> bytes:
    sb = admin_client()
    return sb.storage.from_(bucket).download(path)


def download_segment(segment_date: date_cls, category: str) -> bytes:
    return download(BUCKET_SEGMENTS, segment_path(segment_date, category))


# ---------------------------------------------------------------------------
# Signed URLs (for emails + listen page)
# ---------------------------------------------------------------------------


def signed_brief_url(user_id: str, brief_date: date_cls, ttl_seconds: int = DEFAULT_SIGNED_URL_TTL) -> str:
    sb = admin_client()
    res = sb.storage.from_(BUCKET_BRIEFS).create_signed_url(
        path=brief_path(user_id, brief_date),
        expires_in=ttl_seconds,
    )
    return res["signedURL"]
