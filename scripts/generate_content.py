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

from core.config import ensure_data_dirs, load_settings  # noqa: E402
from agents.content_agent import ContentAgent  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate high-intent SaaS social content")
    parser.add_argument("--topic", required=True, help="Angle or topic for the post")
    parser.add_argument("--platform", default="x", choices=["x", "linkedin"])
    parser.add_argument("--context", default="", help="Extra brief (trend, competitor, etc.)")
    args = parser.parse_args()

    ensure_data_dirs()
    agent = ContentAgent()

    print(f"Generating for platform={args.platform} …")
    try:
        pieces = agent.generate(args.topic, platform=args.platform, extra_context=args.context)
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
