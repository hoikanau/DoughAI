"""Render a verdict dict as a Markdown report."""

from __future__ import annotations

DISCLAIMER = (
    "> **Not financial advice.** This is an informational signal derived from "
    "public data and probabilistic language-model reasoning. Treat it as one "
    "input among many, not a directive."
)


def render_markdown(verdict: dict) -> str:
    ticker = verdict.get("ticker", "?")
    lines = [f"# {ticker} — {verdict.get('verdict', 'UNKNOWN')}", ""]
    lines.append(DISCLAIMER)
    lines.append("")

    if verdict.get("parse_error"):
        lines.append("**The agent's response could not be parsed as JSON.**")
        lines.append("")
        lines.append("Raw response:")
        lines.append("```")
        lines.append(verdict.get("raw_response", ""))
        lines.append("```")
        return "\n".join(lines)

    lines.append(f"- **Confidence:** {verdict.get('confidence')}")
    lines.append(f"- **Time horizon:** {verdict.get('time_horizon')}")
    lines.append(f"- **Generated at:** {verdict.get('generated_at')}")
    lines.append("")
    lines.append("## Reasoning")
    lines.append(verdict.get("reasoning", ""))
    lines.append("")

    evidence = verdict.get("supporting_evidence") or []
    if evidence:
        lines.append("## Supporting evidence")
        lines.extend(f"- {item}" for item in evidence)
        lines.append("")

    risks = verdict.get("key_risks") or []
    if risks:
        lines.append("## Key risks")
        lines.extend(f"- {item}" for item in risks)
        lines.append("")

    sources = verdict.get("sources") or []
    if sources:
        lines.append("## Sources")
        lines.extend(f"- {item}" for item in sources)
        lines.append("")

    return "\n".join(lines)
