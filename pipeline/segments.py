"""
pipeline/segments.py — per-topic script + MP3 generation.

One segment per topic per day. Shared across every user who subscribes to that
topic. Segments are short (~60-90s), focused on 1-2 top stories, written so
they can stand alone when stitched into a user's personalized brief.
"""

from __future__ import annotations

import json
import os
from datetime import date as date_cls

import requests
from google import genai

from pipeline import audio, content, db, storage

CATEGORIES = ["POLITICS", "BUSINESS", "FINANCE", "MOVIES", "AI"]

CATEGORY_INTROS = {
    "POLITICS": "In politics today",
    "BUSINESS": "In business",
    "FINANCE": "In finance",
    "MOVIES": "In entertainment",
    "AI": "And on the A.I. front",
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def build_segment_instructions(category: str, stories_count: int, has_continuity: bool) -> str:
    """
    Returns the LLM system prompt for one topic segment.
    Short, fact-only, spelled-out numbers, clean hand-off tone.
    """
    intro_phrase = CATEGORY_INTROS.get(category.upper(), f"In {category.lower()} news")
    return (
        f"Write a short audio news segment for the {category} category.\n"
        "\n"
        "Constraints:\n"
        f"- Open with '{intro_phrase}...' or a very close variant.\n"
        f"- Cover {stories_count} top story/stories from the JSON lineup I'll provide.\n"
        "- Two to three sentences per story: the headline event, key specifics (quotes, numbers, names), and brief factual context.\n"
        "- Fact-only. Do not add opinions, speculation, tension, or emotional language.\n"
        "- Do NOT invent facts — only use what's in the lineup JSON.\n"
        "- Do NOT number the stories. Let them flow naturally.\n"
        "- IMPORTANT: Spell out ALL numbers as words. Examples: 2026 -> 'twenty twenty-six', $3.5 billion -> 'three point five billion dollars', 47% -> 'forty-seven percent'. This applies to dates, dollar amounts, statistics, scores, and all other numbers.\n"
        "- If the news involves President Trump, do not call him 'former president' — he is the current president.\n"
        "- Close the segment cleanly in one sentence so it can transition into the next topic. "
        "Good: 'That's the latest from business.' Bad: ending mid-thought.\n"
        "- Target length: about 60 to 90 seconds of spoken audio (roughly 150-220 words).\n"
        "- Output must be plain text suitable for ElevenLabs narration. No headers, no markdown, no stage directions.\n"
        + ("- CONTINUITY: If today's story is a development of something covered in the previous-segments JSON, briefly frame it as a developing story (e.g., 'Following yesterday's report on X, today Y.').\n" if has_continuity else "")
    )


# ---------------------------------------------------------------------------
# Script generation
# ---------------------------------------------------------------------------


def generate_segment_script(
    category: str,
    stories: list[dict],
    continuity: list[dict] | None = None,
    *,
    provider: str | None = None,
    openai_key: str | None = None,
    openai_model: str = "gpt-4.1-mini",
    gemini_key: str | None = None,
    gemini_model: str = "gemini-2.5-pro",
) -> str:
    """Ask the configured LLM to write a short segment script."""
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    instructions = build_segment_instructions(
        category=category,
        stories_count=len(stories),
        has_continuity=bool(continuity),
    )

    payload = {"category": category, "stories": stories}
    if continuity:
        payload["previous_segments"] = continuity

    user_prompt = "Here is today's lineup as JSON:\n" + json.dumps(payload, ensure_ascii=False)

    if provider == "openai":
        key = openai_key or os.getenv("OPENAI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("Missing OPENAI_API_KEY")
        return _call_openai(instructions, user_prompt, key, openai_model)
    else:
        key = gemini_key or os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            raise RuntimeError("Missing GEMINI_API_KEY")
        return _call_gemini(instructions, user_prompt, key, gemini_model)


def _call_openai(instructions: str, user_prompt: str, api_key: str, model: str) -> str:
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "input": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.4,
        },
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    text_parts = []
    for out in data.get("output", []):
        for c in out.get("content", []):
            if c.get("type") == "output_text":
                text_parts.append(c.get("text", ""))
    script = "\n".join(text_parts).strip()
    if not script:
        raise RuntimeError("OpenAI returned no output_text")
    return script


def _call_gemini(instructions: str, user_prompt: str, api_key: str, model: str) -> str:
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=[instructions, user_prompt],
    )
    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty response")
    return text


# ---------------------------------------------------------------------------
# Full daily segment generation loop
# ---------------------------------------------------------------------------


def generate_daily_segments(
    today: date_cls,
    items: list[dict],
    needed_categories: list[str] | None = None,
    stories_per_segment: int = 2,
) -> dict[str, dict]:
    """
    For each needed category, generate (or skip if already done) a segment.
    Returns {category: segment_row}.
    """
    results: dict[str, dict] = {}
    todo = [c.upper() for c in (needed_categories or CATEGORIES)]

    for category in todo:
        if db.segment_exists(today, category):
            print(f"[segments] {category}: already generated for {today}, skipping")
            continue

        lineup = content.build_lineup(items, [category], stories_per_category=stories_per_segment)
        stories = lineup.get(category, [])
        if not stories:
            print(f"[segments] {category}: no breaking stories today, skipping")
            continue

        content.enrich_lineup({category: stories})

        continuity = db.recent_segments(category, days=3)

        print(f"[segments] {category}: generating script from {len(stories)} stor{'y' if len(stories) == 1 else 'ies'}")
        script_text = generate_segment_script(category, stories, continuity)

        print(f"[segments] {category}: generating MP3 ({len(script_text)} chars)")
        mp3_bytes = audio.generate_mp3_bytes(script_text)

        print(f"[segments] {category}: uploading to Storage")
        mp3_path = storage.upload_segment(today, category, mp3_bytes)

        stories_meta = [
            {
                "title": s["title"],
                "url": s["url"],
                "snippet": s.get("snippet", ""),
            }
            for s in stories
        ]

        row = db.save_segment(today, category, script_text, mp3_path, stories_meta)
        results[category] = row
        print(f"[segments] {category}: saved as {row.get('id')}")

    return results
