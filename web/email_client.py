"""Thin wrapper around the Resend API for sending the digest email."""

from __future__ import annotations

import os

import resend


def send_email(to: str, subject: str, html: str) -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]
    from_address = os.environ.get("DIGEST_FROM_EMAIL", "DoughAI <digest@resend.dev>")
    resend.Emails.send(
        {
            "from": from_address,
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )
