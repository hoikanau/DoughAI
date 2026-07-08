# Agent instructions for this repo

- System design: `docs/ARCHITECTURE.md`
- Current status and next steps: `PROGRESS.md`

## Session convention: keep `PROGRESS.md` current

Sessions in this repo don't share memory with each other. `PROGRESS.md` is the hard-memory
substitute — read it first, and keep it accurate as you go, since it's the only thing carrying
context into the next session (this one resuming later, or a fresh one).

- **Start of session:** read `PROGRESS.md` before doing anything else.
- **Whenever something changes that the next session would need to know** — code written, a
  decision made, a PR opened/merged, a blocker found, a plan revised — update `PROGRESS.md` to
  reflect it. Don't wait until the end of a long session to do this once; update it as you go, the
  same turn the change happens.
- **Keep it a status doc, not a transcript.** Write current state and the concrete next step(s),
  not a play-by-play of how you got there. Prefer overwriting stale entries to appending endlessly.
- **Commit `PROGRESS.md`** along with (or immediately after) the change it describes, so a fresh
  session pulling the repo sees it.
