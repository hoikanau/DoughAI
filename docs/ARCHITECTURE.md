# DoughAI — Architecture & Data Pipeline

DoughAI is an AI agent that watches market trends across price action, fundamentals,
news, and macro data, and produces an evidence-backed **Buy / Hold / Sell / Watch**
call with a confidence score, reasoning, and citations. This document lays out the
end-to-end pipeline: where data comes from, how it's processed, how the agent
reasons over it, and how recommendations are evaluated and delivered.

> **Not financial advice.** DoughAI produces informational signals derived from
> public data and probabilistic language-model reasoning. Every output must carry
> that disclaimer and should be treated as one input among many, not a directive.

## 1. High-level pipeline

```
 ┌────────────────┐   ┌───────────────────┐   ┌────────────────────┐   ┌─────────────────────┐   ┌───────────────┐
 │  1. INGESTION   │→  │  2. STORAGE        │→  │  3. FEATURE LAYER  │→  │  4. AGENT REASONING │→  │  5. DELIVERY  │
 │  market, fund-  │   │  time-series +     │   │  indicators,       │   │  tool-using LLM     │   │  report, API, │
 │  amentals, news,│   │  vector store for  │   │  ratios, sentiment │   │  agent(s) w/ RAG,   │   │  bot, alerts  │
 │  macro, filings │   │  unstructured text │   │  scores, regimes   │   │  structured output  │   │               │
 └────────────────┘   └───────────────────┘   └────────────────────┘   └─────────────────────┘   └───────────────┘
                                                                                  ↑
                                                                    ┌─────────────────────────┐
                                                                    │ 6. BACKTEST / EVAL LOOP  │
                                                                    │ scores past calls,       │
                                                                    │ feeds accuracy back in   │
                                                                    └─────────────────────────┘
```

Everything is scheduled/event-driven (section 7) and every recommendation is
logged so its later outcome can be scored (section 6) — this is what prevents
the agent from being a black box that just sounds confident.

## 2. Data ingestion — sources by category

No single API covers price, fundamentals, news, and macro well, so the agent
pulls from a small set of complementary sources per category rather than one
"do everything" provider.

| Category | Primary source | Backup / supplement | What it provides | Cadence |
|---|---|---|---|---|
| **Price/volume (OHLCV)** | [Alpha Vantage](https://www.alphavantage.co) or [Massive/Polygon.io](https://polygon.io) | `yfinance` (free, good for prototyping) | Intraday + daily OHLCV, adjusted close, splits/dividends | Real-time to 1-min (paid) / 15-min delayed (free) |
| **Technical indicators** | Computed locally from OHLCV (`pandas-ta`) | Alpha Vantage `TECHNICAL_INDICATORS` endpoint | RSI, MACD, SMA/EMA, Bollinger Bands, ATR, volume trend | Derived on each refresh |
| **Fundamentals** | [Financial Modeling Prep](https://financialmodelingprep.com) | Alpha Vantage `OVERVIEW`/`EARNINGS` | Income statement, balance sheet, cash flow, ratios (P/E, P/B, PEG, D/E), analyst estimates | Quarterly (event-driven on earnings) |
| **Regulatory filings** | [SEC EDGAR full-text search + XBRL API](https://www.sec.gov/edgar/sec-api-documentation) (free) | — | 10-K, 10-Q, 8-K, Form 4 (insider trades), 13F (institutional holdings) | Event-driven (filing date) |
| **News** | Alpha Vantage `NEWS_SENTIMENT` or FMP news endpoint | Finnhub, NewsAPI | Headlines + article text tagged to tickers | Streaming/hourly |
| **Social sentiment** | StockTwits API | Reddit (PRAW, r/stocks, r/wallstreetbets), X/Twitter API | Retail sentiment, unusual chatter volume | Hourly |
| **Macro** | [FRED (Federal Reserve Economic Data)](https://fred.stlouisfed.org/docs/api/fred/) (free) | Treasury.gov yield curve | CPI, Fed funds rate, unemployment, yield curve | Daily/monthly per series |
| **Earnings calls** | FMP transcripts endpoint | — | Management commentary, Q&A tone | Event-driven (earnings date) |

**Practical note on cost:** start on free tiers (`yfinance`, Alpha Vantage free,
SEC EDGAR, FRED — all $0) to build and validate the pipeline; upgrade to paid
tiers (FMP, Massive/Polygon) only once the signal has proven itself in backtests,
since real-time/high-volume data is the most expensive line item.

Several of these providers (Alpha Vantage, FMP) now expose **MCP servers**, so
they can be wired directly into a Claude Agent SDK tool loop instead of hand-rolled
REST clients — worth using if you build the agent on Claude.

## 3. Storage layer

- **Time-series data** (prices, indicators, fundamentals snapshots): Postgres +
  TimescaleDB, or just partitioned Parquet files read via DuckDB if you want to
  avoid running a DB server initially. Keyed by `(ticker, timestamp)`.
- **Unstructured text** (news articles, filings, earnings transcripts): stored
  raw (S3/local disk) + chunked and embedded into a vector store (pgvector,
  Chroma, or LanceDB for a single-node setup) for retrieval-augmented generation.
- **Recommendation log**: append-only table of every call the agent makes
  (ticker, timestamp, verdict, confidence, evidence used, model version) — this
  is what the backtest/eval loop scores later. Never overwrite past calls.

## 4. Feature engineering layer

Turns raw data into the numeric/categorical signals the agent reasons over:

- **Technical**: trend (SMA/EMA crossovers), momentum (RSI, MACD, stochastic),
  volatility (ATR, Bollinger width), volume anomalies (relative volume vs.
  20-day average).
- **Fundamental**: valuation ratios vs. sector median, revenue/earnings growth
  trend, margin trend, debt trend, insider buy/sell ratio (Form 4).
- **Sentiment**: news sentiment score (FinBERT or an LLM classifier scoring
  each headline -1..+1), social chatter volume z-score, sentiment momentum
  (is it improving or deteriorating week over week).
- **Macro regime**: simple classifier (e.g., rate environment, yield curve
  shape) so the agent can contextualize a stock call against the broader tape
  rather than in isolation.

These become structured inputs (a per-ticker feature snapshot, e.g. JSON) that
get attached to the agent's prompt/tool results — the agent should never be
asked to eyeball raw price CSVs.

## 5. Agent reasoning layer (the core of "the agent")

This is where an LLM (Claude) does the actual synthesis. Two viable shapes,
in increasing sophistication:

**V1 — single agent, tool-augmented.** One Claude agent with tools:
`get_price_history`, `get_fundamentals`, `get_news`, `get_sentiment`,
`get_macro_context`, `search_filings` (RAG over embedded 10-K/10-Q chunks).
The agent pulls what it needs per ticker and produces a structured verdict.
Fast to build (Claude Agent SDK + MCP tool servers from section 2), good MVP.

**V2 — role-specialized multi-agent** (pattern used by systems like
MarketSenseAI and AlphaAgent): separate sub-agents for technical analysis,
fundamental analysis, sentiment/news analysis, and risk — each produces its
own short brief, and a final "portfolio manager" agent reconciles them into
one verdict. This reduces the chance that one loud signal (e.g. news) drowns
out a contradicting one (e.g. deteriorating fundamentals), and makes
disagreement between agents itself a useful signal (low agreement → lower
confidence).

**Output contract** (always structured, e.g. JSON via tool-call/schema):

```json
{
  "ticker": "AAPL",
  "verdict": "BUY | HOLD | SELL | WATCH",
  "confidence": 0.0,
  "time_horizon": "short_term | swing | long_term",
  "reasoning": "2-4 sentence synthesis",
  "supporting_evidence": ["...", "..."],
  "key_risks": ["...", "..."],
  "sources": ["url1", "url2"],
  "generated_at": "ISO-8601"
}
```

Grounding rules: the agent must cite the specific data point behind each
claim (no unsupported assertions), and must explicitly flag when signals
across categories disagree rather than papering over it.

## 6. Backtest & evaluation loop

An agent that has never been checked against history shouldn't be trusted.
Two complementary checks, both necessary:

1. **Signal backtesting** (offline, before trusting a feature at all): replay
   historical data through the feature layer with a framework like
   [`vectorbt`](https://vectorbt.dev) or `backtrader` to see whether a given
   technical/fundamental signal historically preceded favorable moves. This
   validates the *inputs*, not the LLM.
2. **Recommendation tracking** (ongoing, on the live system): every entry in
   the recommendation log gets revisited N days later against actual price
   movement, producing a running hit-rate / calibration score per verdict
   type and per confidence bucket. This is what tells you whether the agent's
   "confidence: 0.8" calls are actually right ~80% of the time — and it's the
   main defense against an agent that just sounds authoritative.

Never let the agent see its own future accuracy stats as "truth to match" —
that's a feedback path that teaches it to hedge rather than to be well-calibrated.

## 7. Scheduling & triggers

- **Scheduled refresh**: nightly full refresh of fundamentals/macro, hourly
  for price/news/sentiment during market hours.
- **Event-driven refresh**: earnings release, 8-K filing, >3% intraday move,
  or a sentiment/volume spike should trigger an immediate re-evaluation of
  that ticker rather than waiting for the next scheduled cycle.
- Orchestration can start as simple cron; move to Prefect/Airflow only once
  you have enough tickers/sources that dependency ordering matters.

## 8. Delivery

- CLI report / Markdown digest to start (cheapest to build and debug).
- Optional: Slack/Discord bot, or a small web dashboard, once the core loop
  is validated. Always render the disclaimer, confidence, and sources
  alongside the verdict — never just the verdict.

## 9. Suggested initial tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python | Best library coverage (`pandas-ta`, `yfinance`, `vectorbt`, finance SDKs) |
| Data fetch | `httpx` + provider SDKs / MCP servers | Async-friendly, MCP lets Claude call these tools directly |
| Storage | Postgres + pgvector (or DuckDB+Parquet for local-only MVP) | One store for structured + embedded text |
| Agent | Claude via Agent SDK, tool-calling, structured output | Matches this repo's ecosystem |
| Backtesting | `vectorbt` | Fast vectorized backtests for signal validation |
| Scheduling | cron → Prefect later | Start simple |

## 10. Phased roadmap

1. **MVP**: one ticker at a time, `yfinance` + Alpha Vantage free tier +
   SEC EDGAR, single tool-using Claude agent, CLI output, recommendation log.
2. **V2**: add news/sentiment sources, technical+fundamental feature layer,
   backtest loop scoring past calls, watchlist of multiple tickers.
3. **V3**: multi-agent reconciliation, event-driven triggers, dashboard/bot
   delivery, portfolio-level view (correlation/risk across watchlist, not
   just single-ticker calls).

## 11. Key risks to design around

- **Hallucinated numbers**: never let the agent state a metric it didn't
  retrieve via a tool call — enforce this with structured tool outputs, not
  free-text recall.
- **Survivorship/backtest overfitting**: validate signals out-of-sample; a
  backtest that looks great in-sample is close to worthless.
- **Data lag vs. real-time claims**: free tiers are often delayed 15+ minutes;
  never present delayed data as real-time.
- **Compliance**: this is informational tooling, not investment advice — keep
  that framing explicit in every output, and don't build in auto-execution of
  trades without a very deliberate, separately-gated design step.

---

Sources consulted: [ScrapingBee — Best Stock Market APIs 2026](https://www.scrapingbee.com/blog/best-stock-market-apis/), [Financial Modeling Prep — Real-Time Stock APIs Comparison](https://site.financialmodelingprep.com/education/other/best-realtime-stock-market-data-apis-in-), [Alpha Vantage](https://www.alphavantage.co/), [MarketSenseAI 2.0 (arXiv:2502.00415)](https://arxiv.org/html/2502.00415v2), [Integrating LLMs in Financial Investments and Market Analysis: A Survey (arXiv:2507.01990)](https://arxiv.org/pdf/2507.01990), [Multi-Agent LLM-Based Stock Market Forecasting (arXiv:2506.16813)](https://arxiv.org/html/2506.16813v1).
