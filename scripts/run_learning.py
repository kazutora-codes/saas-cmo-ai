#!/usr/bin/env python3
"""Brick 9 CLI: extract learnings from outcomes and print durable rules."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.learn import learnings_prompt_block, run_learning_cycle  # noqa: E402
from analytics.store import evaluate_outcomes, import_from_queue, init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-improvement learning cycle")
    parser.add_argument("--import-queue", action="store_true")
    parser.add_argument("--llm", action="store_true", help="Optional LLM refine")
    parser.add_argument("--show", action="store_true", help="Print prompt block only")
    args = parser.parse_args()

    if args.show:
        block = learnings_prompt_block()
        print(block or "(no learnings yet)")
        return

    init_db()
    if args.import_queue:
        n = import_from_queue()
        print(f"Imported {n} from queue")
    evaluate_outcomes()
    data = run_learning_cycle(use_llm=args.llm)
    print(f"Saved → {data.get('_path')}")
    print(f"Stats: {data.get('stats')}")
    print("\nDO:")
    for r in data.get("rules_do") or []:
        print(f"  • {r}")
    print("DON'T:")
    for r in data.get("rules_dont") or []:
        print(f"  • {r}")
    if data.get("topic_boost"):
        print("Topic boost:", ", ".join(data["topic_boost"]))
    if data.get("topic_avoid"):
        print("Topic avoid:", ", ".join(data["topic_avoid"]))
    if data.get("winning_hooks"):
        print("\nWinning hooks:")
        for h in data["winning_hooks"]:
            print(f"  - {h}")
    for n in data.get("notes") or []:
        print(f"note: {n}")


if __name__ == "__main__":
    main()
