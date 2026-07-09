"""FastAPI app: the Phase 2 dashboard + digest cron endpoint.

Reuses doughai.agent.run_agent() (the same tool-use loop the CLI uses) and
caches verdicts in Postgres (web/db.py) so page loads don't always pay for a
fresh agent run.
"""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from doughai.agent import run_agent
from doughai.tools import get_price_series

from . import db
from .digest import run_digest

BASE_DIR = Path(__file__).parent

app = FastAPI(title="DoughAI")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _cache_hours() -> float:
    return float(os.environ.get("DOUGHAI_CACHE_HOURS", "12"))


def _is_stale(verdict: dict | None) -> bool:
    if not verdict:
        return True
    generated_at = verdict.get("generated_at")
    if not generated_at:
        return True
    try:
        generated = datetime.datetime.fromisoformat(generated_at)
    except ValueError:
        return True
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=datetime.timezone.utc)
    age = datetime.datetime.now(datetime.timezone.utc) - generated
    return age > datetime.timedelta(hours=_cache_hours())


def _watchlist_tickers() -> list[str]:
    raw = os.environ.get("DIGEST_TICKERS", "")
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


@app.get("/")
def index(request: Request):
    tickers = _watchlist_tickers()
    watchlist = [(ticker, db.get_latest_verdict(ticker)) for ticker in tickers]
    return templates.TemplateResponse(
        request, "index.html", {"watchlist": watchlist}
    )


@app.get("/ticker/{ticker}")
def ticker_page(request: Request, ticker: str):
    ticker = ticker.upper()
    verdict = db.get_latest_verdict(ticker)
    if _is_stale(verdict):
        verdict = run_agent(ticker)
        db.save_verdict(verdict)
    history = db.get_history(ticker, limit=10)
    price_series = get_price_series(ticker)
    return templates.TemplateResponse(
        request,
        "ticker.html",
        {
            "ticker": ticker,
            "verdict": verdict,
            "history": history,
            "price_series_json": json.dumps(price_series),
        },
    )


@app.post("/ticker/{ticker}/refresh")
def refresh_ticker(ticker: str):
    ticker = ticker.upper()
    verdict = run_agent(ticker)
    db.save_verdict(verdict)
    return JSONResponse({"status": "ok", "verdict": verdict})


@app.get("/api/cron/digest")
def cron_digest(authorization: str | None = Header(default=None)):
    cron_secret = os.environ.get("CRON_SECRET")
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(status_code=401, detail="unauthorized")
    count = run_digest()
    return JSONResponse({"status": "ok", "tickers_sent": count})
