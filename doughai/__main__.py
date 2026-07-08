"""CLI entry point: python -m doughai TICKER [TICKER ...]"""

from __future__ import annotations

import argparse
import sys

from .agent import run_agent
from .recommendation_log import log_verdict
from .report import render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="doughai",
        description="Produce an evidence-backed Buy/Hold/Sell/Watch verdict for one or more tickers.",
    )
    parser.add_argument("tickers", nargs="+", help="Stock ticker symbols, e.g. AAPL MSFT")
    parser.add_argument(
        "--log-path",
        default=None,
        help="Override the recommendation log path (default: data/recommendations.jsonl)",
    )
    args = parser.parse_args()

    for ticker in args.tickers:
        ticker = ticker.upper()
        print(f"Analyzing {ticker}...", file=sys.stderr)
        verdict = run_agent(ticker)
        if args.log_path:
            log_verdict(verdict, path=args.log_path)
        else:
            log_verdict(verdict)
        print(render_markdown(verdict))
        print()


if __name__ == "__main__":
    main()
