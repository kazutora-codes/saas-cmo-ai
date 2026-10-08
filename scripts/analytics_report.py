#!/usr/bin/env python3
"""Brick 7 CLI: weekly what-worked report + few-shot refresh."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.report import generate_report, save_report  # noqa: E402
from analytics.store import evaluate_outcomes, import_from_queue, init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate analytics learning report")
    parser.add_argument("--days", type=int, default=7, help="Lookback window")
    parser.add_argument("--import-queue", action="store_true", help="Import queue posts first")
    args = parser.parse_args()

    init_db()
    if args.import_queue:
        n = import_from_queue()
        print(f"Imported {n} from queue")
    evaluate_outcomes()
    report = generate_report(days=args.days)
    path = save_report(report)

    print(f"Window: last {report['window_days']} days")
    print(f"Posts: {report['totals']['posts']}")
    print(f"Labels: {report['totals']['by_label']}")
    print(f"Platforms: {report['totals']['by_platform']}")
    print("\nWhy winners:")
    for line in report["why_winners"]:
        print(f"  - {line}")
    print("Why losers:")
    for line in report["why_losers"]:
        print(f"  - {line}")
    if report["winners"]:
        print("\nTop winners:")
        for w in report["winners"][:3]:
            print(f"  [{w.get('platform')}] {str(w.get('body', ''))[:80]}")
    print(f"\nFew-shot examples: {len(report.get('few_shot') or [])}")
    print(f"Saved → {path}")
    print(f"Few-shot → {path.parent / 'few_shot.json'}")


if __name__ == "__main__":
    main()
