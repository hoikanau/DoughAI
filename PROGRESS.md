# DoughAI — Progress

_Last updated: 2026-07-08 — PR #2 merged, this file created._

## Current status: Phase 1 complete and merged

DoughAI's deployment plan (decided with the user) sequences the work as:
1. **Phase 1 — prove the agent, not the UI:** CLI tool, one ticker at a time, no auth/hosting.
2. **Phase 2 — dashboard + digest:** one small backend serving both a web dashboard (ticker
   search, chart, verdict + history) and a scheduled digest (email/Slack/Discord), so there's one
   agent core and two thin outputs. Deploy cheaply (Vercel/Render/Fly.io).
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
with a real `ANTHROPIC_API_KEY` and confirmed it works.

## Next step

**Still open, and the actual go/no-go gate for Phase 2:** run the CLI against a handful more real
tickers and manually sanity-check that the verdicts and citations are actually good (numbers match
a real source, sources resolve, reasoning matches the verdict, confidence is calibrated) — not just
that it runs without erroring. Once that's done, move to Phase 2 (dashboard + digest).

## Environment notes (avoid re-discovering these)

- **Cloud/sandboxed sessions can't fully test this.** This environment's outbound network policy
  blocks both `fc.yahoo.com` (yfinance's backend) and `www.sec.gov`/`data.sec.gov` (SEC EDGAR) —
  confirmed via the proxy status endpoint, not a code bug. There's also usually no
  `ANTHROPIC_API_KEY` configured in a fresh sandboxed session. **Real testing has to happen on the
  user's machine**, not in a cloud session — see the README's setup steps.
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
