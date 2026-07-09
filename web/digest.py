"""Builds and sends the scheduled digest email.

Triggered by the /api/cron/digest route (web/app.py), which Vercel Cron
calls on a schedule. Reuses the same doughai.agent.run_agent() core as the
CLI and the dashboard -- this module is just the "gather + email" glue.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from doughai.agent import run_agent

from . import db
from .email_client import send_email

TEMPLATES_DIR = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)


def _watchlist_tickers() -> list[str]:
    raw = os.environ.get("DIGEST_TICKERS", "")
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


def _is_from_today(verdict: dict) -> bool:
    generated_at = verdict.get("generated_at")
    if not generated_at:
        return False
    try:
        generated_date = datetime.datetime.fromisoformat(generated_at).date()
    except ValueError:
        return False
    return generated_date == datetime.datetime.now(datetime.timezone.utc).date()


def _verdict_for_digest(ticker: str) -> dict:
    cached = db.get_latest_verdict(ticker)
    if cached and _is_from_today(cached):
        return cached
    verdict = run_agent(ticker)
    db.save_verdict(verdict)
    return verdict


def run_digest() -> int:
    """Send the digest email. Returns the number of tickers included."""
    tickers = _watchlist_tickers()
    to_email = os.environ["DIGEST_TO_EMAIL"]

    verdicts = [_verdict_for_digest(ticker) for ticker in tickers]

    template = _env.get_template("digest_email.html")
    html = template.render(
        verdicts=verdicts,
        generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )
    today = datetime.date.today().isoformat()
    send_email(to_email, f"DoughAI daily digest — {today}", html)
    return len(verdicts)
