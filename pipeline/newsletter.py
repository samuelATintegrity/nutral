"""
pipeline/newsletter.py — render the HTML email for one user's brief.

Uses plain f-strings (no Jinja) for zero deps. Inline CSS for email-client
compatibility. Matches the landing page aesthetic: Fraunces serif, warm ivory,
olive accent.
"""

from __future__ import annotations

from datetime import date as date_cls
from html import escape

from pipeline.db import CANONICAL_ORDER


# ---------------------------------------------------------------------------
# Category display names
# ---------------------------------------------------------------------------

CATEGORY_LABELS = {
    "POLITICS": "Politics",
    "BUSINESS": "Business",
    "FINANCE": "Finance",
    "MOVIES": "Movies",
    "AI": "AI",
}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_newsletter(
    *,
    first_name: str,
    brief_date: date_cls,
    segments: list[dict],
    listen_url: str,
    unsubscribe_url: str,
    account_url: str,
) -> str:
    """
    Render the HTML body for the brief email.

    segments: list of rows from `segments` table, already ordered.
              Each must have .category and .stories (list of {title, url, snippet}).
    """
    weekday = brief_date.strftime("%A")
    pretty_date = brief_date.strftime("%B %-d") if _supports_dash_d() else brief_date.strftime("%B %#d") if _is_windows() else brief_date.strftime("%B %d").lstrip("0")

    topic_labels = ", ".join(CATEGORY_LABELS.get(s["category"], s["category"].title()) for s in segments)

    greeting_name = escape(first_name or "there")

    story_blocks_html = "\n".join(_render_story_block(s) for s in segments)

    return f"""\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Your Nūtral brief</title>
</head>
<body style="margin:0;padding:0;background:#F7F4EC;font-family:'Iowan Old Style',Georgia,serif;color:#1A1A1A;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F7F4EC;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:620px;background:#FCFAF3;border:1px solid #D9D3C4;border-radius:12px;overflow:hidden;">

          <!-- Header / wordmark -->
          <tr>
            <td style="padding:28px 32px 12px 32px;border-bottom:1px solid #D9D3C4;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-family:'Iowan Old Style',Georgia,serif;font-size:22px;font-weight:600;letter-spacing:-0.02em;color:#1A1A1A;">Nūtral</td>
                  <td align="right" style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#5C5A55;letter-spacing:0.08em;text-transform:uppercase;">{escape(weekday)}, {escape(pretty_date)}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Greeting -->
          <tr>
            <td style="padding:40px 32px 16px 32px;">
              <h1 style="margin:0 0 10px 0;font-family:'Iowan Old Style',Georgia,serif;font-size:32px;font-weight:500;letter-spacing:-0.02em;line-height:1.15;color:#1A1A1A;">Good morning, {greeting_name}.</h1>
              <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#5C5A55;">Your brief for today covers {escape(topic_labels)}.</p>
            </td>
          </tr>

          <!-- Listen CTA -->
          <tr>
            <td style="padding:8px 32px 24px 32px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="background:#3A5A40;border-radius:8px;">
                    <a href="{escape(listen_url, quote=True)}" style="display:inline-block;padding:14px 24px;font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:500;color:#F7F4EC;text-decoration:none;letter-spacing:0.01em;">▶ Listen (about 5 minutes)</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Stories -->
          <tr>
            <td style="padding:8px 32px 24px 32px;">
              {story_blocks_html}
            </td>
          </tr>

          <!-- Divider -->
          <tr>
            <td style="padding:0 32px;">
              <hr style="border:none;border-top:1px solid #D9D3C4;margin:0;">
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:24px 32px 32px 32px;">
              <p style="margin:0 0 8px 0;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.6;color:#5C5A55;">
                <a href="{escape(account_url, quote=True)}" style="color:#3A5A40;text-decoration:underline;">Manage your topics</a>
                &nbsp;·&nbsp;
                <a href="{escape(unsubscribe_url, quote=True)}" style="color:#5C5A55;text-decoration:underline;">Unsubscribe</a>
              </p>
              <p style="margin:0;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.6;color:#8a8680;">Nūtral · nutral.news · Your news, no outrage included.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def render_subject(first_name: str, brief_date: date_cls) -> str:
    weekday = brief_date.strftime("%A")
    pretty = brief_date.strftime("%B %-d") if _supports_dash_d() else brief_date.strftime("%B %d").lstrip("0")
    name = first_name.strip() if first_name else ""
    if name:
        return f"{name}, your brief for {weekday}, {pretty}"
    return f"Your brief for {weekday}, {pretty}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _render_story_block(segment: dict) -> str:
    category = segment.get("category", "")
    label = CATEGORY_LABELS.get(category, category.title())
    stories = segment.get("stories") or []

    story_lines = "\n".join(_render_story_line(s) for s in stories)

    return f"""\
<div style="margin:0 0 24px 0;">
  <p style="margin:0 0 10px 0;font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:500;letter-spacing:0.12em;text-transform:uppercase;color:#3A5A40;">{escape(label)}</p>
  {story_lines}
</div>"""


def _render_story_line(story: dict) -> str:
    title = escape(story.get("title", ""))
    url = escape(story.get("url", "#"), quote=True)
    snippet = escape((story.get("snippet") or "").strip())
    snippet_html = f'<p style="margin:4px 0 0 0;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.55;color:#5C5A55;">{snippet}</p>' if snippet else ""
    return f"""\
<div style="margin:0 0 14px 0;">
  <a href="{url}" style="font-family:'Iowan Old Style',Georgia,serif;font-size:18px;font-weight:500;line-height:1.3;color:#1A1A1A;text-decoration:none;">{title}</a>
  {snippet_html}
</div>"""


def _supports_dash_d() -> bool:
    """%-d works on Linux/macOS, fails on Windows."""
    import platform
    return platform.system() != "Windows"


def _is_windows() -> bool:
    import platform
    return platform.system() == "Windows"
