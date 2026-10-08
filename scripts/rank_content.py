#!/usr/bin/env python3
"""Brick 4 CLI: score and rank content variants (from file or stdin JSON)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.quality_gate import pick_winner, rank_variants  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank SaaS content variants by quality gates")
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to content JSON from generate_content.py (or omit for stdin)",
    )
    parser.add_argument("--no-llm", action="store_true", help="Heuristic scores only")
    parser.add_argument(
        "--out",
        default="",
        help="Write ranked JSON to this path (default: alongside input as *.ranked.json)",
    )
    args = parser.parse_args()

    if args.path:
        raw = Path(args.path).read_text(encoding="utf-8")
        data = json.loads(raw)
    else:
        data = json.load(sys.stdin)

    pieces = data.get("pieces") if isinstance(data, dict) else data
    if not isinstance(pieces, list):
        print("Expected {pieces: [...]} or a list of variants", file=sys.stderr)
        sys.exit(1)

    ranked = rank_variants(pieces, use_llm=False if args.no_llm else None)
    winner = ranked[0] if ranked else None

    out = {
        "topic": data.get("topic") if isinstance(data, dict) else None,
        "platform": data.get("platform") if isinstance(data, dict) else None,
        "ranked": ranked,
        "winner": winner,
    }

    if args.out:
        out_path = Path(args.out)
    elif args.path:
        p = Path(args.path)
        out_path = p.with_name(p.stem + ".ranked.json")
    else:
        out_path = None

    if out_path:
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"Saved → {out_path}")

    print(f"Variants ranked: {len(ranked)}")
    for r in ranked:
        q = r["quality"]
        status = "PASS" if q["passed"] else "FAIL"
        print(
            f"  #{r['rank']} [{status}] overall={q['overall']:.2f} "
            f"intent={q['intent']:.2f} orig={q['originality']:.2f} "
            f"humor={q['humor']:.2f} brand={q['brand_fit']:.2f}  ({q['source']})"
        )
        body = (r.get("body") or "")[:100].replace("\n", " ")
        print(f"      {body}")

    if winner:
        print("\nWinner:")
        print(winner.get("body", ""))
    else:
        print("\nNo publishable winner (all failed gates).")


if __name__ == "__main__":
    main()
