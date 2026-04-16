"""
pipeline/db.py — Supabase admin client for the Nūtral pipeline.

Uses the SERVICE ROLE key (NOT anon) so the pipeline can read/write all tables
bypassing RLS. The service role key must only live in GitHub Actions secrets or
the local .env — never ship it to any browser.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from supabase import Client, create_client


@lru_cache(maxsize=1)
def admin_client() -> Client:
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def fetch_active_users() -> list[dict]:
    """Return rows where status='active' and topics array is non-empty."""
    sb = admin_client()
    res = (
        sb.table("users")
        .select("id, email, first_name, topics, timezone, status")
        .eq("status", "active")
        .execute()
    )
    users = [u for u in (res.data or []) if u.get("topics")]
    print(f"[db] {len(users)} active user(s) with topics")
    return users


# ---------------------------------------------------------------------------
# Segments (shared daily content)
# ---------------------------------------------------------------------------


def segment_exists(segment_date: date, category: str) -> bool:
    sb = admin_client()
    res = (
        sb.table("segments")
        .select("id")
        .eq("segment_date", segment_date.isoformat())
        .eq("category", category.upper())
        .limit(1)
        .execute()
    )
    return bool(res.data)


def save_segment(
    segment_date: date,
    category: str,
    script_text: str,
    mp3_path: str,
    stories: list[dict],
    duration_ms: int | None = None,
) -> dict:
    sb = admin_client()
    row = {
        "segment_date": segment_date.isoformat(),
        "category": category.upper(),
        "script_text": script_text,
        "mp3_path": mp3_path,
        "stories": stories,
        "duration_ms": duration_ms,
    }
    res = sb.table("segments").insert(row).execute()
    return (res.data or [{}])[0]


def fetch_segments(segment_date: date, categories: list[str]) -> list[dict]:
    """Fetch segments for a given date, ordered by Nūtral's canonical topic order."""
    sb = admin_client()
    wanted = [c.upper() for c in categories]
    res = (
        sb.table("segments")
        .select("*")
        .eq("segment_date", segment_date.isoformat())
        .in_("category", wanted)
        .execute()
    )
    by_cat = {row["category"]: row for row in (res.data or [])}
    return [by_cat[c] for c in CANONICAL_ORDER if c in by_cat]


def recent_segments(category: str, days: int = 3) -> list[dict]:
    """For continuity context: previous N days' segments in one category."""
    sb = admin_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    res = (
        sb.table("segments")
        .select("segment_date, script_text, stories")
        .eq("category", category.upper())
        .gte("segment_date", cutoff.isoformat())
        .order("segment_date", desc=True)
        .limit(days)
        .execute()
    )
    return res.data or []


# ---------------------------------------------------------------------------
# Briefs (per-user delivery records)
# ---------------------------------------------------------------------------


def brief_exists(user_id: str, brief_date: date) -> bool:
    sb = admin_client()
    res = (
        sb.table("briefs")
        .select("id")
        .eq("user_id", user_id)
        .eq("brief_date", brief_date.isoformat())
        .limit(1)
        .execute()
    )
    return bool(res.data)


def save_brief(
    user_id: str,
    brief_date: date,
    segment_ids: list[str],
    opening_mp3_path: str | None,
    stitched_mp3_path: str,
    newsletter_html: str,
    sent_at: datetime | None = None,
) -> dict:
    sb = admin_client()
    row = {
        "user_id": user_id,
        "brief_date": brief_date.isoformat(),
        "segment_ids": segment_ids,
        "opening_mp3_path": opening_mp3_path,
        "stitched_mp3_path": stitched_mp3_path,
        "newsletter_html": newsletter_html,
        "sent_at": sent_at.isoformat() if sent_at else None,
    }
    res = sb.table("briefs").insert(row).execute()
    return (res.data or [{}])[0]


def mark_brief_sent(brief_id: str, sent_at: datetime) -> None:
    sb = admin_client()
    sb.table("briefs").update({"sent_at": sent_at.isoformat()}).eq("id", brief_id).execute()


# ---------------------------------------------------------------------------
# Canonical display order for topics across Nūtral
# ---------------------------------------------------------------------------

CANONICAL_ORDER = ["POLITICS", "BUSINESS", "FINANCE", "MOVIES", "AI"]
