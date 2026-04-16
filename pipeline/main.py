"""
pipeline/main.py — daily orchestrator for Nūtral briefs.

Run with:   python -m pipeline.main
or:         python -m pipeline.main --dry-run

Two phases:
  1. Shared segment generation  — ONE MP3 per topic that any user wants today.
  2. Per-user delivery          — stitch (opening + segments + closing), send email.

Idempotent at the phase-1 level (segments table is UNIQUE on date+category) and
at the phase-2 level (briefs table is UNIQUE on user_id+date). Safe to re-run.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import date as date_cls
from datetime import datetime, timezone

from dotenv import load_dotenv

from pipeline import audio, content, db, delivery, newsletter, segments, stitch, storage

STATIC_CLOSING_PATH = "closing.mp3"  # stored in BUCKET_SEGMENTS under this key


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main(dry_run: bool = False, only_user_email: str | None = None) -> int:
    load_dotenv()
    today = date_cls.today()

    print(f"[main] Nutral pipeline starting for {today.isoformat()}")
    print(f"[main] dry_run={dry_run}, only_user_email={only_user_email}")

    users = db.fetch_active_users()
    if only_user_email:
        users = [u for u in users if (u.get("email") or "").lower() == only_user_email.lower()]
        print(f"[main] Filtered to {len(users)} user(s) matching email={only_user_email}")
    if not users:
        print("[main] No active users — nothing to do")
        return 0

    # Which topics do we need to generate today?
    needed = sorted({c.upper() for u in users for c in (u.get("topics") or [])})
    print(f"[main] Topics needed today: {needed}")

    # -------------------- PHASE 1: shared segment generation --------------------
    if not dry_run:
        raw_items = content.fetch_items(categories=needed)
        items = content.deduplicate(raw_items)
        print(f"[main] fetched {len(raw_items)} raw, {len(items)} after dedup")

        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_key:
            items = content.classify_items(items, api_key=gemini_key)
        else:
            print("[main] WARNING: no GEMINI_API_KEY, skipping classification")

        try:
            segments.generate_daily_segments(today, items, needed_categories=needed)
        except Exception as e:
            print(f"[main] FATAL during segment generation: {e!r}")
            traceback.print_exc()
            return 1
    else:
        print("[main] dry-run: skipping segment generation")

    # -------------------- PHASE 2: per-user delivery --------------------
    succeeded = 0
    failed = 0
    skipped = 0

    # Pre-download the static closing once per run
    try:
        closing_bytes = storage.download(storage.BUCKET_SEGMENTS, STATIC_CLOSING_PATH)
    except Exception as e:
        print(f"[main] WARNING: could not load static closing ({e!r}) — briefs will end without outro")
        closing_bytes = None

    for user in users:
        uid = user["id"]
        email = user["email"]
        try:
            if db.brief_exists(uid, today):
                print(f"[user {email}] brief already exists for {today}, skipping")
                skipped += 1
                continue

            user_segments = db.fetch_segments(today, user["topics"])
            if not user_segments:
                print(f"[user {email}] no segments available for their topics, skipping")
                skipped += 1
                continue

            print(f"[user {email}] building brief with {len(user_segments)} segment(s): "
                  f"{[s['category'] for s in user_segments]}")

            if dry_run:
                print(f"[user {email}] DRY RUN — would generate opening, stitch, and email")
                succeeded += 1
                continue

            # 1. Personalized opening (short — ~5 sec / ~50 chars of TTS)
            opening_text = _build_opening(user.get("first_name") or "there", today)
            opening_bytes = audio.generate_mp3_bytes(opening_text, use_ssml=False)
            opening_path_str = storage.upload_opening(uid, today, opening_bytes)

            # 2. Stitch opening + segments + closing
            parts = [opening_bytes]
            for seg in user_segments:
                parts.append(storage.download_segment(today, seg["category"]))
            if closing_bytes:
                parts.append(closing_bytes)
            stitched_bytes = stitch.concat_mp3s(parts, silence_ms=400)

            # 3. Upload final brief
            stitched_path_str = storage.upload_brief(uid, today, stitched_bytes)

            # 4. Render newsletter HTML
            listen_url = storage.signed_brief_url(uid, today)
            account_url = f"https://nutral.news/account"
            unsubscribe_url = f"https://nutral.news/unsubscribe?u={uid}"

            html = newsletter.render_newsletter(
                first_name=user.get("first_name") or "there",
                brief_date=today,
                segments=user_segments,
                listen_url=listen_url,
                unsubscribe_url=unsubscribe_url,
                account_url=account_url,
            )
            subject = newsletter.render_subject(user.get("first_name") or "", today)

            # 5. Save brief row FIRST so we never double-send on retry
            saved = db.save_brief(
                user_id=uid,
                brief_date=today,
                segment_ids=[s["id"] for s in user_segments],
                opening_mp3_path=opening_path_str,
                stitched_mp3_path=stitched_path_str,
                newsletter_html=html,
            )

            # 6. Send email
            resp = delivery.send_email(to=email, subject=subject, html=html)
            print(f"[user {email}] Resend id: {resp.get('id')}")

            db.mark_brief_sent(saved["id"], datetime.now(timezone.utc))
            succeeded += 1
            print(f"[user {email}] DONE")

        except Exception as e:
            failed += 1
            print(f"[user {email}] FAILED: {e!r}")
            traceback.print_exc()
            continue  # never kill the whole run because of one user

    print(f"[main] Done. succeeded={succeeded} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_opening(first_name: str, today: date_cls) -> str:
    """Short personalized opening line. Keep under ~15 words."""
    weekday = today.strftime("%A")
    return f"Good morning, {first_name}. Here's your brief for {weekday}."


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Skip TTS, uploads, and email sends")
    parser.add_argument("--only", help="Only process the user with this email address")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run, only_user_email=args.only))
