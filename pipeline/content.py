"""
pipeline/content.py — RSS fetching, deduplication, classification, scraping.

Ported from daily_brief.py (Artificial Tribune) with these Nutral-specific changes:
- fetch_items() accepts a category filter so we only pull feeds we need today
- build_lineup() accepts a dynamic PLAN instead of using a hardcoded global
- Classification category rules trimmed to Nutral's five launch categories
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import trafilatura
from google import genai

LOOKBACK_HOURS = 36

TRACKING_PARAMS = {"fbclid", "gclid", "ref"}
TRACKING_PREFIXES = ("utm_",)

LIVE_UPDATE_PATTERNS = [
    r"\blive updates\b",
    r"\blive blog\b",
    r"\blive\b",
]

# Default feed file location (relative to repo root)
DEFAULT_FEEDS_FILE = Path(__file__).resolve().parent.parent / "feeds.txt"


# ---------------------------------------------------------------------------
# URL / title normalization  (reused as-is from daily_brief.py)
# ---------------------------------------------------------------------------


def canonicalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        q = []
        for k, v in parse_qsl(p.query, keep_blank_values=True):
            kl = k.lower()
            if kl in TRACKING_PARAMS:
                continue
            if any(kl.startswith(prefix) for prefix in TRACKING_PREFIXES):
                continue
            q.append((k, v))
        new_query = urlencode(q, doseq=True)
        return urlunparse((p.scheme, p.netloc, p.path, p.params, new_query, ""))
    except Exception:
        return url


def normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t


def stable_id(title: str, url: str) -> str:
    base = normalize_title(title) + "|" + canonicalize_url(url)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


def looks_like_live_update(title: str) -> bool:
    t = title.lower()
    return any(re.search(pat, t) for pat in LIVE_UPDATE_PATTERNS)


def parse_entry_datetime(entry):
    tt = entry.get("published_parsed") or entry.get("updated_parsed")
    if not tt:
        return None
    return datetime.fromtimestamp(time.mktime(tt), tz=timezone.utc)


# ---------------------------------------------------------------------------
# Feed loading + ingest
# ---------------------------------------------------------------------------


def load_categorized_feeds(feeds_file: Path = DEFAULT_FEEDS_FILE, categories: list[str] | None = None):
    """
    Parse feeds.txt. If `categories` is provided, return only matching feeds.
    Format:  CATEGORY|https://example.com/rss
    """
    feeds = []
    wanted = {c.upper() for c in categories} if categories else None

    with open(feeds_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" not in line:
                raise ValueError(f"Bad line in feeds.txt (missing '|'): {line}")
            category, url = line.split("|", 1)
            category = category.strip().upper()
            url = url.strip()
            if wanted is None or category in wanted:
                feeds.append((category, url))
    return feeds


def fetch_items(categories: list[str] | None = None, lookback_hours: int = LOOKBACK_HOURS) -> list[dict]:
    """
    Fetch raw items from RSS feeds filtered to the requested categories.
    If categories is None, fetch everything in feeds.txt.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    feeds = load_categorized_feeds(categories=categories)

    raw = []
    for category, url in feeds:
        feed = feedparser.parse(url)
        for e in feed.entries:
            title = (e.get("title") or "").strip()
            link = (e.get("link") or "").strip()
            published_dt = parse_entry_datetime(e)

            if not title or not link or not published_dt:
                continue
            if published_dt < cutoff:
                continue

            c_url = canonicalize_url(link)
            snippet = (e.get("summary") or "").strip()[:200]
            raw.append({
                "id": stable_id(title, c_url),
                "title": title,
                "url": c_url,
                "published_utc": published_dt.isoformat(),
                "category": category,
                "feed": url,
                "is_live_update": looks_like_live_update(title),
                "source_type": "rss",
                "snippet": snippet,
            })
    return raw


def deduplicate(raw_items: list[dict]) -> list[dict]:
    dedup: dict[str, dict] = {}
    for it in raw_items:
        existing = dedup.get(it["id"])
        if not existing or it["published_utc"] > existing["published_utc"]:
            dedup[it["id"]] = it
    items = list(dedup.values())
    items.sort(key=lambda x: x["published_utc"], reverse=True)
    return items


# ---------------------------------------------------------------------------
# Classification (Gemini breaking-event filter) — trimmed to Nutral's 5 topics
# ---------------------------------------------------------------------------


def classify_items(items: list[dict], api_key: str, model: str = "gemini-2.5-flash") -> list[dict]:
    """
    Ask Gemini to classify each headline as breaking_event / opinion / study / analysis.
    Return only the breaking_events. On API failure, return items unfiltered.
    """
    if not items:
        return items

    candidates = [
        {"index": i, "title": it["title"], "snippet": it.get("snippet", ""), "category": it["category"]}
        for i, it in enumerate(items)
    ]

    prompt_system = (
        "You are a news classifier. For each headline+snippet, classify it as exactly one of:\n"
        '- "breaking_event": A factual news event that happened or is happening right now.\n'
        '- "opinion": An opinion piece, editorial, column, or commentary.\n'
        '- "study": A research study, scientific paper, report, or survey result.\n'
        '- "analysis": In-depth analysis, explainer, feature piece, or listicle.\n'
        "\n"
        "Additional filtering rules by category (use the category field):\n"
        '- POLITICS: Only "breaking_event" for concrete policy actions, elections, diplomatic developments. Exclude speculation, horse-race coverage, op-eds.\n'
        '- BUSINESS: Only "breaking_event" if it is a specific company action (M&A, layoffs, earnings surprise, executive change, product launch). Exclude general business strategy essays.\n'
        '- FINANCE: Only "breaking_event" if it is a Federal Reserve announcement, inflation report, labor market report, or mortgage rate change. Exclude general market commentary.\n'
        '- MOVIES: Only "breaking_event" if it is a U.S. movie production announcement, greenlit project, or major director/actor attachment. Exclude reviews, box office reports, festival coverage, TV shows, and international films.\n'
        '- AI: Only "breaking_event" if it is a new AI capability, model release, or breakthrough. Exclude opinion pieces about AI risks/ethics.\n'
        "\n"
        'Respond with a JSON array of objects: [{"index": 0, "classification": "breaking_event"}, ...]\n'
        "Only output valid JSON. No explanation. No markdown formatting."
    )
    prompt_user = json.dumps(candidates, ensure_ascii=False)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[prompt_system, prompt_user],
        )
        text = (getattr(response, "text", None) or "").strip()

        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
            text = text.strip()

        json_match = re.search(r"\[.*\]", text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

        classifications = json.loads(text)
        breaking = {c["index"] for c in classifications if c.get("classification") == "breaking_event"}
        filtered = [it for i, it in enumerate(items) if i in breaking]
        print(f"[classify] {len(items)} candidates -> {len(filtered)} breaking events")
        return filtered
    except Exception as e:
        print(f"[classify] failed ({e!s}); using all items")
        return items


# ---------------------------------------------------------------------------
# Lineup construction — parameterized per user / per topic
# ---------------------------------------------------------------------------


def rank_items(items: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    ranked = []
    for it in items:
        pub = datetime.fromisoformat(it["published_utc"])
        hours_old = (now - pub).total_seconds() / 3600
        recency = max(0.0, 1.0 - hours_old / LOOKBACK_HOURS)
        ranked.append((recency, it))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in ranked]


def build_lineup(items: list[dict], categories: list[str], stories_per_category: int = 2) -> dict[str, list[dict]]:
    """
    Pick the top `stories_per_category` stories per requested category.
    Skips live-update feeds.
    """
    ranked = rank_items(items)
    wanted = {c.upper() for c in categories}

    by_cat: dict[str, list[dict]] = {c: [] for c in wanted}
    used_ids: set[str] = set()
    for it in ranked:
        cat = it["category"].upper()
        if cat not in wanted:
            continue
        if it["id"] in used_ids:
            continue
        if it.get("is_live_update"):
            continue
        if len(by_cat[cat]) < stories_per_category:
            by_cat[cat].append(it)
            used_ids.add(it["id"])

    return by_cat


# ---------------------------------------------------------------------------
# Article scraping (trafilatura)
# ---------------------------------------------------------------------------


def scrape_article_content(url: str, max_chars: int = 1500) -> str:
    """Fetch article body text. Best-effort; returns empty string on failure."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return (text or "")[:max_chars]
    except Exception:
        return ""


def enrich_lineup(lineup: dict[str, list[dict]]) -> None:
    """Attach .article_content to every story in the lineup, mutating in place."""
    total = fetched = 0
    for stories in lineup.values():
        for item in stories:
            content = scrape_article_content(item["url"])
            item["article_content"] = content
            total += 1
            if content:
                fetched += 1
    print(f"[scrape] {fetched}/{total} articles fetched")
