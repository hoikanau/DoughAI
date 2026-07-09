"""Data-fetching tools for the DoughAI agent.

Each function here is exposed to Claude as a tool. Keep return values as
plain JSON-serializable dicts/lists — the agent should never be asked to
eyeball raw price CSVs (see docs/ARCHITECTURE.md section 4).
"""

from __future__ import annotations

import os
import time

import requests
import yfinance as yf

SEC_USER_AGENT = os.environ.get(
    "SEC_EDGAR_USER_AGENT", "DoughAI research-agent contact@example.com"
)

_TICKER_CIK_CACHE: dict[str, str] | None = None


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def get_price_history(ticker: str, period: str = "6mo") -> dict:
    """Fetch OHLCV history for a ticker and derive basic technical indicators."""
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return {"error": f"no price history found for {ticker}"}

    closes = hist["Close"].tolist()
    volumes = hist["Volume"].tolist()
    latest_close = round(closes[-1], 2)
    period_start_close = round(closes[0], 2)
    pct_change = round((latest_close - period_start_close) / period_start_close * 100, 2)

    avg_volume_20d = round(sum(volumes[-20:]) / min(20, len(volumes)), 0)
    latest_volume = volumes[-1]
    relative_volume = (
        round(latest_volume / avg_volume_20d, 2) if avg_volume_20d else None
    )

    return {
        "ticker": ticker,
        "period": period,
        "latest_close": latest_close,
        "period_start_close": period_start_close,
        "period_pct_change": pct_change,
        "sma_20": _sma(closes, 20),
        "sma_50": _sma(closes, 50),
        "rsi_14": _rsi(closes),
        "latest_volume": int(latest_volume),
        "avg_volume_20d": int(avg_volume_20d),
        "relative_volume": relative_volume,
        "52wk_high": round(max(closes), 2),
        "52wk_low": round(min(closes), 2),
    }


def get_price_series(ticker: str, period: str = "6mo") -> list[dict]:
    """Fetch a plain date/close series for charting.

    Not registered as an agent tool -- the agent gets summarized stats via
    get_price_history(); this is purely for the dashboard's price chart.
    """
    hist = yf.Ticker(ticker).history(period=period)
    if hist.empty:
        return []
    return [
        {"date": index.strftime("%Y-%m-%d"), "close": round(close, 2)}
        for index, close in hist["Close"].items()
    ]


def get_fundamentals(ticker: str) -> dict:
    """Fetch valuation and fundamental metrics for a ticker."""
    info = yf.Ticker(ticker).info
    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        return {"error": f"no fundamentals found for {ticker}"}

    fields = [
        "longName",
        "sector",
        "industry",
        "marketCap",
        "trailingPE",
        "forwardPE",
        "priceToBook",
        "pegRatio",
        "debtToEquity",
        "returnOnEquity",
        "profitMargins",
        "revenueGrowth",
        "earningsGrowth",
        "dividendYield",
        "beta",
    ]
    return {"ticker": ticker, **{f: info.get(f) for f in fields}}


def get_news(ticker: str, limit: int = 5) -> list[dict]:
    """Fetch recent news headlines tagged to a ticker."""
    raw_items = yf.Ticker(ticker).news or []
    items = []
    for raw in raw_items[:limit]:
        # yfinance has shipped a couple of different news payload shapes;
        # unwrap the nested "content" key when present.
        content = raw.get("content", raw)
        items.append(
            {
                "title": content.get("title"),
                "publisher": (content.get("provider") or {}).get("displayName")
                or raw.get("publisher"),
                "link": (content.get("canonicalUrl") or {}).get("url")
                or raw.get("link"),
                "published": content.get("pubDate") or raw.get("providerPublishTime"),
            }
        )
    return items


def _load_ticker_cik_map() -> dict[str, str]:
    global _TICKER_CIK_CACHE
    if _TICKER_CIK_CACHE is not None:
        return _TICKER_CIK_CACHE
    resp = requests.get(
        "https://www.sec.gov/files/company_tickers.json",
        headers={"User-Agent": SEC_USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _TICKER_CIK_CACHE = {
        row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in data.values()
    }
    return _TICKER_CIK_CACHE


def search_filings(ticker: str, forms: str = "10-K,10-Q,8-K", limit: int = 5) -> list[dict]:
    """Look up recent SEC EDGAR filings (10-K/10-Q/8-K/etc.) for a ticker."""
    cik_map = _load_ticker_cik_map()
    cik = cik_map.get(ticker.upper())
    if not cik:
        return [{"error": f"no CIK found for ticker {ticker}"}]

    resp = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik}.json",
        headers={"User-Agent": SEC_USER_AGENT},
        timeout=10,
    )
    resp.raise_for_status()
    recent = resp.json().get("filings", {}).get("recent", {})

    wanted_forms = {f.strip().upper() for f in forms.split(",")}
    results = []
    for form, date, accession, doc in zip(
        recent.get("form", []),
        recent.get("filingDate", []),
        recent.get("accessionNumber", []),
        recent.get("primaryDocument", []),
    ):
        if form.upper() not in wanted_forms:
            continue
        accession_nodash = accession.replace("-", "")
        results.append(
            {
                "form": form,
                "filing_date": date,
                "url": (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(cik)}/{accession_nodash}/{doc}"
                ),
            }
        )
        if len(results) >= limit:
            break
    return results or [{"error": f"no matching filings found for {ticker}"}]


TOOL_DEFINITIONS = [
    {
        "name": "get_price_history",
        "description": (
            "Get recent OHLCV price history and derived technical indicators "
            "(SMA20/50, RSI14, relative volume, 52-week range) for a stock ticker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"},
                "period": {
                    "type": "string",
                    "description": "yfinance period string, e.g. 1mo, 6mo, 1y",
                    "default": "6mo",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_fundamentals",
        "description": (
            "Get valuation and fundamental metrics for a stock ticker: market cap, "
            "P/E, P/B, PEG, debt/equity, margins, growth rates, dividend yield, beta."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_news",
        "description": "Get recent news headlines tagged to a stock ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"},
                "limit": {"type": "integer", "description": "Max headlines to return", "default": 5},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "search_filings",
        "description": (
            "Look up recent SEC EDGAR filings (10-K, 10-Q, 8-K, etc.) for a stock "
            "ticker, returning filing type, date, and document URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol, e.g. AAPL"},
                "forms": {
                    "type": "string",
                    "description": "Comma-separated form types to include",
                    "default": "10-K,10-Q,8-K",
                },
                "limit": {"type": "integer", "description": "Max filings to return", "default": 5},
            },
            "required": ["ticker"],
        },
    },
]

TOOL_IMPLEMENTATIONS = {
    "get_price_history": get_price_history,
    "get_fundamentals": get_fundamentals,
    "get_news": get_news,
    "search_filings": search_filings,
}


def run_tool(name: str, tool_input: dict) -> object:
    impl = TOOL_IMPLEMENTATIONS.get(name)
    if impl is None:
        return {"error": f"unknown tool {name}"}
    try:
        return impl(**tool_input)
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent as a tool error
        return {"error": f"{name} failed: {exc}"}
