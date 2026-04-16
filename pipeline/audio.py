"""
pipeline/audio.py — ElevenLabs TTS for Nūtral (single voice).

Ported from daily_brief.py elevenlabs_generate_mp3(). Main differences:
- Returns bytes instead of writing to disk (caller decides where to store)
- Uses eleven_multilingual_v2 (stable) since Nūtral is single-voice, not dialogue
"""

from __future__ import annotations

import os
import re
from xml.sax.saxutils import escape as xml_escape

import requests

ELEVEN_TTS_URL_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


# ---------------------------------------------------------------------------
# SSML helpers (ported as-is from daily_brief.py)
# ---------------------------------------------------------------------------


def is_headerish(paragraph: str) -> bool:
    p = paragraph.strip()
    if not p or "." in p or len(p) > 40:
        return False
    letters = re.sub(r"[^A-Za-z]", "", p)
    if not letters:
        return False
    upper_ratio = sum(1 for ch in letters if ch.isupper()) / max(1, len(letters))
    return upper_ratio >= 0.85


def plain_text_to_ssml(
    text: str,
    story_break_ms: int = 600,
    section_break_ms: int = 900,
) -> str:
    """Wrap plain text in SSML, adding breaks between paragraphs."""
    t = (text or "").replace("\r\n", "\n").strip()
    t = re.sub(r"(?m)^\s*---\s*$", "", t)
    t = re.sub(r"\n{4,}", "\n\n\n", t).strip()

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", t) if p.strip()]
    out = ["<speak>"]
    for i, p in enumerate(paragraphs):
        safe = xml_escape(p).replace("\n", " ")
        out.append(safe)
        if i < len(paragraphs) - 1:
            ms = section_break_ms if is_headerish(p) else story_break_ms
            out.append(f'<break time="{ms}ms" />')
    out.append("</speak>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------


def generate_mp3_bytes(
    text: str,
    api_key: str | None = None,
    voice_id: str | None = None,
    model_id: str = "eleven_multilingual_v2",
    use_ssml: bool = True,
    stability: float = 0.45,
    similarity_boost: float = 0.8,
) -> bytes:
    """
    Call ElevenLabs TTS and return the raw MP3 bytes.
    Reads ELEVEN_API_KEY / ELEVEN_VOICE_ID from env if not passed.
    """
    api_key = api_key or os.getenv("ELEVEN_API_KEY", "").strip()
    voice_id = voice_id or os.getenv("ELEVEN_VOICE_ID", "").strip()
    if not api_key:
        raise RuntimeError("Missing ELEVEN_API_KEY")
    if not voice_id:
        raise RuntimeError("Missing ELEVEN_VOICE_ID")

    payload_text = plain_text_to_ssml(text) if use_ssml else text

    r = requests.post(
        ELEVEN_TTS_URL_TEMPLATE.format(voice_id=voice_id),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        json={
            "text": payload_text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        },
        timeout=180,
    )
    r.raise_for_status()
    return r.content
