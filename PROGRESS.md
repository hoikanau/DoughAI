# DoughAI — Progress

_Last updated: 2026-07-09 — Phase 2 (dashboard + digest backend) built, not yet deployed/merged._

## Current status: Phase 2 built, needs real deployment + testing

DoughAI's deployment plan (decided with the user) sequences the work as:
1. **Phase 1 — prove the agent, not the UI:** CLI tool, one ticker at a time, no auth/hosting.
2. **Phase 2 — dashboard + digest:** one small backend serving both a web dashboard (ticker
   search, chart, verdict + history) and a scheduled digest, so there's one agent core and two
   thin outputs.
3. **Phase 3 — public-product hardening:** only once there's real usage — accounts/auth,
   rate-limiting, compliance disclaimers, then (maybe) a wrapped-webview mobile app.

A native mobile app and a chat bot (Slack/Discord/Telegram) were explicitly deferred — see
`docs/ARCHITECTURE.md` for the underlying agent design this all builds on.

**Phase 1 is done and merged** (PR #2 → `main`, squashed history: `69a98dc`, `b9631fb`, `584a292`).
Built:
- `doughai/tools.py` — `get_price_history`/`get_fundamentals`/`get_news` (yfinance),
  `search_filings` (SEC EDGAR)
- `doughai/agent.py` — Claude tool-use loop (`claude-opus-4-8`), produces the structured
  `{ticker, verdict, confidence, reasoning, supporting_evidence, key_risks, sources, ...}` JSON
  from `docs/ARCHITECTURE.md` section 5
- `doughai/report.py` — renders that JSON to Markdown, always with the disclaimer
- `doughai/recommendation_log.py` — append-only JSONL log, one line per verdict
- `doughai/__main__.py` — `python -m doughai TICKER [TICKER ...]`, loads `.env` via
  `python-dotenv` automatically

**Verified:** unit-level pieces (indicator math, JSON parsing, Markdown rendering, log writing, CLI
wiring) tested with synthetic/mocked data. User ran it locally end-to-end against a real ticker
with a real `ANTHROPIC_API_KEY` and confirmed it works. The user decided the "run a handful more
real tickers and sanity-check quality" gate wasn't worth blocking on, since the CLI already accepts
multiple tickers in one invocation — moved straight to Phase 2 instead.

**Phase 2 is built on branch `claude/progress-md-review-iyu4nn`, not yet committed/pushed/reviewed
as a PR.** Stack, chosen with the user via explicit questions: FastAPI + Jinja2 (server-rendered,
no JS build step), Supabase Postgres for storage, Resend for email, Vercel for hosting +
Cron-triggered digest. See `docs/ARCHITECTURE.md` and the approved plan for full rationale. Built:
- `web/app.py` — FastAPI routes: `GET /` (watchlist overview), `GET /ticker/{ticker}` (cached
  verdict or live `run_agent()` call + price chart + history), `POST /ticker/{ticker}/refresh`
  (force a fresh run), `GET /api/cron/digest` (Vercel Cron target, gated on
  `Authorization: Bearer $CRON_SECRET`)
- `web/db.py` — Postgres storage (`psycopg`) replacing the CLI's JSONL log for the deployed app;
  schema in `schema.sql` (one `recommendations` table). **Deliberately not unified** with
  `doughai/recommendation_log.py` — the CLI keeps its local JSONL log for ad-hoc runs, the web app
  has its own DB-backed log. Uses Supabase's transaction-pooler connection string, not the direct
  one (serverless = many short-lived connections).
- `web/digest.py` + `web/email_client.py` — gathers watchlist verdicts (reusing a same-day cached
  one if present), renders `web/templates/digest_email.html`, sends via Resend.
- `web/templates/` (`base.html`, `index.html`, `ticker.html` with a Chart.js price chart,
  `digest_email.html`) + `web/static/style.css`.
- `doughai/tools.py` — added `get_price_series()`, a plain (non-agent-tool) helper for the chart.
- `api/index.py` + `vercel.json` — Vercel Python/ASGI entrypoint, catch-all rewrite, 60s
  `maxDuration` (agent runs are slow), daily cron calling `/api/cron/digest`.
- `requirements.txt`, `.env.example`, `README.md` updated with the new deps/env vars and setup
  steps (Supabase project + `schema.sql`, Resend key, Vercel env vars + cron).

**Verified in-sandbox:** dependencies install cleanly; `vercel.json`/`schema.sql` are syntactically
valid; all four routes (including `CRON_SECRET` auth enforcement — 401 with no/wrong header, 200
with the right one) pass a `TestClient` smoke test with `run_agent`/`db`/`run_digest` mocked out.

## Next step

**Not yet done, and this is the real go/no-go gate for Phase 2 (same shape as Phase 1's):**
1. User provisions a Supabase project, runs `schema.sql` against it, gets a Resend API key, and
   fills in `.env` (see the new "Phase 2" section of `.env.example`).
2. Run `uvicorn web.app:app --reload` locally against real data and eyeball the dashboard — does
   the chart render, does a ticker page load a real verdict, does `/api/cron/digest` actually send
   an email.
3. Deploy to Vercel (`vercel.json` is already set up — catch-all rewrite, cron schedule, function
   timeout), set the env vars there too, confirm the cron fires and the live site works.
4. Once that's confirmed working, commit is already staged for push — get it reviewed/merged (no
   PR opened yet as of this update).

**Cannot be done in a cloud/sandboxed session** — same reason as Phase 1, now extended to Supabase
and Resend too: this environment's outbound network policy blocks the hosts Phase 2 needs
(Anthropic, yfinance, SEC EDGAR, and now Supabase/Resend), so nothing past the mocked smoke test
above could be verified here. Real testing happens on the user's machine or a Vercel preview
deploy.

## Environment notes (avoid re-discovering these)

- **Cloud/sandboxed sessions can't fully test this.** This environment's outbound network policy
  blocks both `fc.yahoo.com` (yfinance's backend) and `www.sec.gov`/`data.sec.gov` (SEC EDGAR) —
  confirmed via the proxy status endpoint, not a code bug. There's also usually no
  `ANTHROPIC_API_KEY` configured in a fresh sandboxed session. **Real testing has to happen on the
  user's machine**, not in a cloud session — see the README's setup steps. Phase 2 adds Supabase
  and Resend to the list of hosts a sandboxed session almost certainly can't reach either — the
  same "mock the network boundary, verify wiring not live behavior" approach applies.
- **`.env` loading is already wired up** — `doughai/__main__.py` calls `load_dotenv()` before
  importing anything that reads env vars. `cp .env.example .env` + fill in `ANTHROPIC_API_KEY` is
  enough; don't reintroduce a version that skips this or the setup step silently breaks again.
- **CodeQL:** this repo's `.github/workflows/security.yml` previously had its own CodeQL job that
  collided with GitHub's Default Setup CodeQL scanning (GitHub only allows one or the other). The
  custom job was removed; the user then disabled Default Setup in repo Settings. If CodeQL comes up
  again, don't re-add a workflow-based CodeQL job without first checking whether Default Setup is
  enabled — check `.github/workflows/security.yml` and ask before changing security-scanning config
  (removing/disabling a security check needs explicit user sign-off, it isn't a routine CI fix).
- **SEC EDGAR requires a real `User-Agent`** (`SEC_EDGAR_USER_AGENT` in `.env`) with an actual
  contact string, or requests get rejected.

## Recent history

- PR #1: initial architecture doc (`docs/ARCHITECTURE.md`) + security-scanning workflow scaffold.
- PR #2: Phase 1 CLI agent (see above), plus two CI fixes along the way — `.env` wasn't actually
  being loaded (fixed with `python-dotenv`), and a CodeQL Default-Setup/workflow conflict (fixed by
  dropping the redundant workflow job + user disabling Default Setup). Merged into `main`.
- PR #3: added `CLAUDE.md`/`PROGRESS.md` for cross-session continuity. Merged into `main`.
- (this session): built Phase 2 end-to-end (see above) on `claude/progress-md-review-iyu4nn`. Not
  yet pushed as a reviewed PR — next session/user picks up at the "Next step" list above.
