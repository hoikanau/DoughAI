# Dough

An AI agent that watches market trends and produces an evidence-backed
Buy/Hold/Sell/Watch call with confidence, reasoning, and citations. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full design.

> **Not financial advice.** Informational only — see the disclaimer in every
> generated report.

## Phase 1 (MVP): CLI verdict tool

Single tool-using Claude agent, one ticker at a time, CLI output, append-only
recommendation log. Data sources: `yfinance` (price/fundamentals/news) and SEC
EDGAR (filings) — both free, no paid API keys required.

### Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY (or run `ant auth login`)
```

### Usage

```bash
python -m doughai AAPL
python -m doughai AAPL MSFT NVDA
```

Each run prints a Markdown report to stdout and appends the structured
verdict to `data/recommendations.jsonl` (never overwritten — this is the log
a future backtest/eval loop scores against).
