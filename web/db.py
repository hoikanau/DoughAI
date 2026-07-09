"""Postgres storage for the web app's verdict cache/history.

Unlike doughai/recommendation_log.py (a local JSONL file for CLI runs), this
talks to Supabase Postgres, since Vercel's serverless filesystem doesn't
persist between requests. See schema.sql for the table this reads/writes.

Uses a fresh short-lived connection per call rather than a process-wide pool
-- Supabase's transaction-pooler connection string (DATABASE_URL) already
pools on the server side, which is what serverless functions need since each
invocation may be a cold start.
"""

from __future__ import annotations

import json
import os

import psycopg
from psycopg.rows import dict_row


def _connect() -> psycopg.Connection:
    database_url = os.environ["DATABASE_URL"]
    return psycopg.connect(database_url, row_factory=dict_row)


def save_verdict(verdict: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            insert into recommendations
                (ticker, verdict, confidence, time_horizon, reasoning, generated_at, raw)
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                verdict.get("ticker"),
                verdict.get("verdict"),
                verdict.get("confidence"),
                verdict.get("time_horizon"),
                verdict.get("reasoning"),
                verdict.get("generated_at"),
                json.dumps(verdict, default=str),
            ),
        )


def get_latest_verdict(ticker: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            """
            select raw from recommendations
            where ticker = %s
            order by generated_at desc
            limit 1
            """,
            (ticker,),
        ).fetchone()
    return row["raw"] if row else None


def get_history(ticker: str, limit: int = 10) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            select raw from recommendations
            where ticker = %s
            order by generated_at desc
            limit %s
            """,
            (ticker, limit),
        ).fetchall()
    return [row["raw"] for row in rows]


def get_watchlist_latest(tickers: list[str]) -> dict[str, dict | None]:
    """Latest cached verdict per ticker, for the homepage overview."""
    return {ticker: get_latest_verdict(ticker) for ticker in tickers}
