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

## Phase 2: dashboard + digest backend

One small FastAPI backend, deployed to Vercel, serving two thin outputs on top of
the same agent core (`doughai/agent.py`, `doughai/tools.py`): a web dashboard
(search a ticker, see its chart/verdict/history) and a daily email digest for a
watchlist. See `docs/ARCHITECTURE.md` and `PROGRESS.md` for the full design.

Unlike the CLI, this needs persistent storage that survives across serverless
invocations, so verdicts are cached in Postgres (Supabase) instead of the local
JSONL log.

### One-time setup

1. **Supabase project**: create one, then run `schema.sql` once against it (Supabase
   SQL editor, or `psql "$DATABASE_URL" -f schema.sql`). Use the *transaction pooler*
   connection string (port 6543) as `DATABASE_URL` — the direct connection string
   will run out of connections under serverless load.
2. **Resend**: create an API key (`RESEND_API_KEY`). The default sender
   (`digest@resend.dev`) works for testing; verify your own domain for production
   and set `DIGEST_FROM_EMAIL`.
3. Fill in the "Phase 2" section of `.env.example` → `.env`: `DATABASE_URL`,
   `RESEND_API_KEY`, `DIGEST_TO_EMAIL`, `DIGEST_TICKERS` (comma-separated watchlist),
   and a `CRON_SECRET` (any random string) for production.

### Local dev

```bash
pip install -r requirements.txt
uvicorn web.app:app --reload
```

Visit `http://localhost:8000`. Search a ticker or open `/ticker/AAPL` directly.
Trigger the digest manually with:

```bash
curl http://localhost:8000/api/cron/digest
```

(`CRON_SECRET` is only enforced when set, so this works locally without it.)

### Deploying to Vercel

1. `vercel link` / import the repo in the Vercel dashboard — it picks up
   `vercel.json` (routes all traffic to `api/index.py`, a 60s function timeout
   for agent runs, and a daily cron hitting `/api/cron/digest`).
2. Set the same env vars from `.env` (plus `ANTHROPIC_API_KEY` and
   `SEC_EDGAR_USER_AGENT`) as Vercel project environment variables, including
   `CRON_SECRET` — Vercel automatically sends it as
   `Authorization: Bearer $CRON_SECRET` on cron-triggered requests.
3. Adjust the cron schedule in `vercel.json` (`crons[0].schedule`) as needed;
   Vercel's Hobby plan cron minimum interval is daily.
