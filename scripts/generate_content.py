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

from core.config import ensure_data_dirs, load_latest_intel, load_settings  # noqa: E402
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate high-intent SaaS social content")
    parser.add_argument("--topic", required=True, help="Angle or topic for the post")
    parser.add_argument("--platform", default="x", choices=["x", "linkedin"])
    parser.add_argument("--context", default="", help="Extra brief (trend, competitor, etc.)")
    parser.add_argument(
        "--with-intel",
        action="store_true",
        help="Inject latest data/intel/latest.json into the prompt",
    )
    args = parser.parse_args()

    ensure_data_dirs()
    agent = ContentAgent()

    extra = args.context
    if args.with_intel:
        intel = _intel_context()
        extra = f"{extra}\n{intel}".strip() if extra else intel

    print(f"Generating for platform={args.platform} …")
    try:
        pieces = agent.generate(args.topic, platform=args.platform, extra_context=extra)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    out_dir = ROOT / load_settings()["paths"]["content_out"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}_{args.platform}.json"
    payload = {
        "topic": args.topic,
        "platform": args.platform,
        "generated_at": stamp,
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
