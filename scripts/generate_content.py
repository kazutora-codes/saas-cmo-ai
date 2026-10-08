#!/usr/bin/env python3
"""Brick 1 CLI: generate high-intent social posts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import (  # noqa: E402
    ensure_data_dirs,
    load_latest_intel,
    load_latest_strategy,
    load_settings,
)
from agents.content_agent import ContentAgent  # noqa: E402


def _intel_context() -> str:
    brief = load_latest_intel()
    if not brief:
        return ""
    parts = ["Market intel context (use if relevant, do not force):"]
    summary = brief.get("llm_summary") or {}
    topics = summary.get("recommended_topics") or brief.get("content_angles") or []
    themes = summary.get("themes") or []
    if themes:
        parts.append("Themes: " + "; ".join(themes[:5]))
    if topics:
        parts.append("Angles: " + "; ".join(str(t) for t in topics[:5]))
    return "\n".join(parts)


def _strategy_context(slot: dict | None = None) -> str:
    plan = load_latest_strategy()
    if not plan:
        return ""
    parts = ["Weekly strategy context:"]
    pillars = plan.get("pillars") or []
    if pillars:
        parts.append(
            "Pillars: "
            + "; ".join(f"{p.get('name')} ({p.get('intent')})" for p in pillars[:5])
        )
    if slot:
        parts.append(
            f"This post: pillar={slot.get('pillar_id')} format={slot.get('format')} "
            f"intent={slot.get('intent')}"
        )
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate high-intent SaaS social content")
    parser.add_argument("--topic", default="", help="Angle or topic for the post")
    parser.add_argument("--platform", default="x", choices=["x", "linkedin"])
    parser.add_argument("--context", default="", help="Extra brief (trend, competitor, etc.)")
    parser.add_argument(
        "--with-intel",
        action="store_true",
        help="Inject latest data/intel/latest.json into the prompt",
    )
    parser.add_argument(
        "--with-strategy",
        action="store_true",
        help="Inject latest data/strategy/latest.json into the prompt",
    )
    parser.add_argument(
        "--from-strategy",
        type=int,
        metavar="N",
        help="Use calendar slot N (0-based) from latest strategy for topic/platform",
    )
    args = parser.parse_args()

    ensure_data_dirs()
    agent = ContentAgent()

    topic = args.topic
    platform = args.platform
    slot = None
    if args.from_strategy is not None:
        plan = load_latest_strategy()
        if not plan or not plan.get("calendar"):
            print("No strategy calendar found. Run: python scripts/run_strategy.py", file=sys.stderr)
            sys.exit(1)
        cal = plan["calendar"]
        if args.from_strategy < 0 or args.from_strategy >= len(cal):
            print(f"Slot out of range 0..{len(cal)-1}", file=sys.stderr)
            sys.exit(1)
        slot = cal[args.from_strategy]
        topic = topic or str(slot.get("topic") or "")
        platform = str(slot.get("platform") or platform)
        args.with_strategy = True

    if not topic:
        print("Provide --topic or --from-strategy N", file=sys.stderr)
        sys.exit(1)

    extra = args.context
    if args.with_intel:
        intel = _intel_context()
        extra = f"{extra}\n{intel}".strip() if extra else intel
    if args.with_strategy:
        strat = _strategy_context(slot)
        extra = f"{extra}\n{strat}".strip() if extra else strat

    print(f"Generating for platform={platform} …")
    try:
        pieces = agent.generate(topic, platform=platform, extra_context=extra)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    out_dir = ROOT / load_settings()["paths"]["content_out"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}_{platform}.json"
    payload = {
        "topic": topic,
        "platform": platform,
        "generated_at": stamp,
        "strategy_slot": slot,
        "pieces": agent.to_dict_list(pieces),
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    for i, p in enumerate(pieces, 1):
        status = "PASS" if p.passed else "FAIL"
        print(f"\n--- variant {i} [{status}] intent={p.intent_score} orig={p.originality_score} ---")
        print(p.body)
        print(f"(provider={p.provider}/{p.model}; {p.notes})")

    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    main()
