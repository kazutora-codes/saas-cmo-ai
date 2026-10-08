#!/usr/bin/env python3
"""Brick 2 CLI: pull free market signals and write a trend brief."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.market_intel import MarketIntelAgent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run free market intelligence brief")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM refinement (ranking + angles only)",
    )
    parser.add_argument(
        "--print-angles",
        action="store_true",
        help="Print recommended content angles only",
    )
    args = parser.parse_args()

    agent = MarketIntelAgent()
    print("Collecting free sources (HN, Lobsters, Reddit, RSS)…")
    brief = agent.run(use_llm=False if args.no_llm else None)
    path = agent.save(brief)

    breakdown = brief.get("source_breakdown", {})
    print(f"Signals: {brief.get('signal_count', 0)}  sources={breakdown}")
    print(f"Saved → {path}")
    print(f"Latest → {path.parent / 'latest.json'}")

    if args.print_angles:
        print("\nContent angles:")
        for i, a in enumerate(brief.get("content_angles", []), 1):
            print(f"  {i}. {a}")
    else:
        print("\nTop signals:")
        for s in brief.get("top_signals", [])[:8]:
            print(
                f"  [{s['source']}] rel={s['relevance']:.2f} score={s['score']:.0f}  {s['title'][:90]}"
            )
        summary = brief.get("llm_summary") or {}
        topics = summary.get("recommended_topics") or summary.get("fallback_topics")
        if topics:
            print("\nRecommended topics:")
            for t in topics:
                print(f"  - {t}")
        elif summary.get("error"):
            print(f"\nLLM refine skipped/failed: {summary['error']}")
            print("Tip: start Ollama or set GROQ_API_KEY / GEMINI_API_KEY, or use --no-llm")

    print(f"\n{json.dumps({'path': str(path), 'signals': brief.get('signal_count')})}")


if __name__ == "__main__":
    main()
