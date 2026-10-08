#!/usr/bin/env python3
"""Brick 6 CLI: enqueue a post (from text, content JSON winner, or strategy slot)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import load_latest_strategy  # noqa: E402
from publish.queue import enqueue, load_queue  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a post to the local publish queue")
    parser.add_argument("--body", default="", help="Post text")
    parser.add_argument("--platform", default="x", choices=["x", "linkedin"])
    parser.add_argument("--topic", default="")
    parser.add_argument(
        "--from-content",
        default="",
        help="Path to generate_content JSON; uses winner or first ranked",
    )
    parser.add_argument(
        "--from-strategy",
        type=int,
        metavar="N",
        help="Use topic from strategy calendar slot N (body still required unless --from-content)",
    )
    parser.add_argument("--schedule", default="", help="Optional ISO date for planned day")
    parser.add_argument("--media", default="", help="Optional media path")
    parser.add_argument("--list", action="store_true", help="List queue and exit")
    args = parser.parse_args()

    if args.list:
        items = load_queue()
        print(f"Queue items: {len(items)}")
        for i in items:
            print(f"  [{i.status:9}] {i.id}  {i.platform:8}  {i.body[:70].replace(chr(10), ' ')}")
        return

    body = args.body
    topic = args.topic
    source = ""

    if args.from_content:
        path = Path(args.from_content)
        data = json.loads(path.read_text(encoding="utf-8"))
        winner = data.get("winner")
        if not winner and data.get("ranked"):
            winner = data["ranked"][0]
        if not winner and data.get("pieces"):
            winner = data["pieces"][0]
        if not winner:
            print("No winner/pieces in content file", file=sys.stderr)
            sys.exit(1)
        body = body or str(winner.get("body") or "")
        topic = topic or str(data.get("topic") or "")
        source = str(path)
        if not args.platform and data.get("platform"):
            args.platform = data["platform"]

    if args.from_strategy is not None:
        plan = load_latest_strategy()
        if not plan or not plan.get("calendar"):
            print("No strategy plan. Run scripts/run_strategy.py", file=sys.stderr)
            sys.exit(1)
        cal = plan["calendar"]
        if args.from_strategy < 0 or args.from_strategy >= len(cal):
            print(f"Slot out of range 0..{len(cal)-1}", file=sys.stderr)
            sys.exit(1)
        slot = cal[args.from_strategy]
        topic = topic or str(slot.get("topic") or "")
        args.platform = str(slot.get("platform") or args.platform)
        args.schedule = args.schedule or str(slot.get("date") or "")
        source = source or f"strategy:{args.from_strategy}"

    if not body.strip():
        print("Provide --body or --from-content", file=sys.stderr)
        sys.exit(1)

    item = enqueue(
        body=body,
        platform=args.platform,
        topic=topic,
        source=source,
        scheduled_for=args.schedule,
        media_path=args.media,
    )
    print(f"Queued {item.id} → {item.platform} ({item.status})")
    print(item.body[:200])
    print(f"Queue size: {len(load_queue())}")


if __name__ == "__main__":
    main()
