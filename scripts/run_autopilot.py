#!/usr/bin/env python3
"""Brick 8 CLI: run autopilot once or in a loop; manage kill switch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.autopilot import Autopilot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SaaS CMO autopilot - intel → strategy → content → publish"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Run a single cycle (default)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously until kill switch or max cycles",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Minutes between cycles in --loop (default from config)",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Stop after N cycles in --loop (0 = unlimited)",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Arm kill switch (creates STOP file)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Clear kill switch",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show kill switch + last cycle state",
    )
    args = parser.parse_args()

    bot = Autopilot()

    if args.stop:
        path = bot.arm_kill()
        print(f"Kill switch ARMED → {path}")
        return

    if args.resume:
        cleared = bot.clear_kill()
        print("Kill switch cleared" if cleared else "Kill switch was not set")
        return

    if args.status:
        killed = bot.is_killed()
        state = bot.load_state()
        print(f"Kill switch: {'ACTIVE' if killed else 'clear'}")
        print(f"Path: {bot.kill_path()}")
        if state.get("last_log"):
            print(f"Last log: {state['last_log']}")
        last = state.get("last_cycle") or {}
        if last:
            print(f"Last cycle: {last.get('started_at')} → {last.get('finished_at')}")
            for s in last.get("steps") or []:
                mark = "OK" if s.get("ok") else "FAIL"
                print(f"  [{mark}] {s.get('name')}: {s.get('detail')}")
        else:
            print("No cycles logged yet.")
        return

    if args.loop:
        bot.run_loop(
            interval_minutes=args.interval or None,
            max_cycles=args.max_cycles or None,
        )
        return

    print("Running one autopilot cycle…")
    if bot.is_killed():
        print(
            f"Kill switch is active ({bot.kill_path()}). "
            "Clear with: python scripts/run_autopilot.py --resume",
            file=sys.stderr,
        )
        sys.exit(2)

    result = bot.run_cycle()
    for s in result.steps:
        mark = "OK" if s.ok else "FAIL"
        print(f"  [{mark}] {s.name}: {s.detail}")
    if result.error:
        print(f"Error: {result.error[:300]}", file=sys.stderr)
        sys.exit(1)
    if result.stopped_by_kill:
        print("Stopped by kill switch.")
        sys.exit(2)

    print(json.dumps({"finished_at": result.finished_at, "steps": len(result.steps)}))


if __name__ == "__main__":
    main()
