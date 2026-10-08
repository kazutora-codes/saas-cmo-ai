#!/usr/bin/env python3
"""Brick 3 CLI: build weekly content pillars + post calendar."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.strategy_agent import StrategyAgent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate weekly SaaS content strategy")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Rule-based plan only (no LLM refine)",
    )
    args = parser.parse_args()

    agent = StrategyAgent()
    print("Building weekly strategy from brand + latest intel…")
    plan = agent.run(use_llm=False if args.no_llm else None)
    path = agent.save(plan)

    print(f"Week start: {plan.week_start}")
    print(f"Product: {plan.product}")
    print(f"Saved → {path}")
    print(f"Latest → {path.parent / 'latest.json'}")

    print("\nPillars:")
    for p in plan.pillars:
        print(f"  [{p.id}] {p.name} ({p.source})")
        print(f"      intent: {p.intent}")

    print("\nCalendar:")
    for c in plan.calendar:
        print(
            f"  {c.date}  {c.platform:8}  pillar={c.pillar_id:12}  [{c.format}]  {c.topic[:70]}"
        )

    if plan.llm_meta:
        print(f"\nLLM: {plan.llm_meta.get('provider')}/{plan.llm_meta.get('model')}")
    elif not args.no_llm:
        print("\n(Rule-based plan — LLM unavailable or failed; use Ollama/Groq/Gemini for refine)")

    print(f"\n{json.dumps({'path': str(path), 'posts': len(plan.calendar)})}")


if __name__ == "__main__":
    main()
