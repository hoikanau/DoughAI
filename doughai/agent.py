"""The DoughAI V1 agent: a single tool-augmented Claude agent that turns a
ticker into a structured Buy/Hold/Sell/Watch verdict.

See docs/ARCHITECTURE.md section 5 for the design this implements.
"""

from __future__ import annotations

import datetime
import json
import os

import anthropic

from .tools import TOOL_DEFINITIONS, run_tool

MODEL = os.environ.get("DOUGHAI_MODEL", "claude-opus-4-8")
MAX_ITERATIONS = 8

SYSTEM_PROMPT = """\
You are DoughAI, an equity research agent. Given a stock ticker, use the \
available tools to gather price/technical data, fundamentals, recent news, \
and SEC filings, then synthesize a single evidence-backed verdict.

Grounding rules:
- Never state a specific number or metric you did not retrieve via a tool call.
- If signals across categories disagree (e.g. strong technicals but \
deteriorating fundamentals), say so explicitly rather than picking a side \
silently, and lower your confidence accordingly.
- Cite the specific data point behind each claim in `supporting_evidence`.
- This is informational only, not financial advice — never phrase the \
verdict as a directive ("you should buy") or hide the disclaimer.

Once you have gathered enough evidence, respond with ONLY a single JSON \
object (no markdown code fences, no other text) matching this exact shape:

{
  "ticker": "AAPL",
  "verdict": "BUY | HOLD | SELL | WATCH",
  "confidence": 0.0,
  "time_horizon": "short_term | swing | long_term",
  "reasoning": "2-4 sentence synthesis",
  "supporting_evidence": ["...", "..."],
  "key_risks": ["...", "..."],
  "sources": ["url1", "url2"],
  "generated_at": "ISO-8601 timestamp"
}
"""


def _extract_text(content: list) -> str:
    return "".join(block.text for block in content if block.type == "text").strip()


def _parse_verdict(ticker: str, raw_text: str) -> dict:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[len("json") :]
        text = text.strip()
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        return {
            "ticker": ticker,
            "verdict": "WATCH",
            "confidence": 0.0,
            "time_horizon": None,
            "reasoning": "Agent did not return parseable JSON.",
            "supporting_evidence": [],
            "key_risks": [],
            "sources": [],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "parse_error": True,
            "raw_response": raw_text,
        }
    verdict.setdefault("generated_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
    verdict.setdefault("ticker", ticker)
    return verdict


def run_agent(ticker: str) -> dict:
    """Run the tool-use loop for a single ticker and return the verdict dict."""
    client = anthropic.Anthropic()
    messages = [
        {
            "role": "user",
            "content": (
                f"Analyze {ticker} and produce a verdict. Use the tools to pull "
                "price history, fundamentals, recent news, and relevant SEC filings "
                "before you decide."
            ),
        }
    ]

    response = None
    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = run_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    }
                )
        messages.append({"role": "user", "content": tool_results})
    else:
        return _parse_verdict(ticker, "")

    return _parse_verdict(ticker, _extract_text(response.content))
