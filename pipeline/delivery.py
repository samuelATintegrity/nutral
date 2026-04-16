"""
pipeline/delivery.py — send the newsletter email via Resend.

Resend docs: https://resend.com/docs
We use the plain REST API (no SDK needed) so the dependency surface stays small.
"""

from __future__ import annotations

import os

import requests

RESEND_API_URL = "https://api.resend.com/emails"

DEFAULT_FROM = "Nūtral <briefs@nutral.news>"
DEFAULT_REPLY_TO = "hello@nutral.news"


def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    from_address: str | None = None,
    reply_to: str | None = None,
    api_key: str | None = None,
) -> dict:
    """
    Send an HTML email via Resend. Returns the Resend response JSON
    (includes an `id` on success).
    """
    api_key = api_key or os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing RESEND_API_KEY")

    payload = {
        "from": from_address or DEFAULT_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if reply_to or DEFAULT_REPLY_TO:
        payload["reply_to"] = reply_to or DEFAULT_REPLY_TO

    r = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()
