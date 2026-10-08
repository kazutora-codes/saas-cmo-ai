#!/usr/bin/env python3
"""Brick 5 CLI: process a clip into a 9:16 short with captions + AI-look check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video.pipeline import ensure_video_dirs, process_video  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FFmpeg pipeline: 9:16 crop, loudnorm, captions, AI-look heuristics"
    )
    parser.add_argument("input", help="Input video path (screen recording, phone clip, etc.)")
    parser.add_argument("-o", "--output", default="", help="Output mp4 path")
    parser.add_argument(
        "-c",
        "--caption",
        default="",
        help="Caption text to burn in (or use --srt)",
    )
    parser.add_argument("--srt", default="", help="Optional SRT subtitle file")
    parser.add_argument(
        "--no-ai-look",
        action="store_true",
        help="Skip AI-look heuristics",
    )
    args = parser.parse_args()

    ensure_video_dirs()
    inp = Path(args.input)
    if not inp.exists():
        print(f"Input not found: {inp}", file=sys.stderr)
        sys.exit(1)

    out = Path(args.output) if args.output else None
    srt = Path(args.srt) if args.srt else None

    print(f"Processing {inp} → 9:16 …")
    try:
        result = process_video(
            inp,
            output_path=out,
            caption_text=args.caption,
            srt_path=srt,
            run_ai_look=not args.no_ai_look,
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    if not result.success:
        print("FFmpeg failed:", file=sys.stderr)
        print(result.log[-1500:], file=sys.stderr)
        sys.exit(1)

    print(f"Output: {result.output}")
    print(f"Size: {result.width}x{result.height}  duration={result.duration}s")
    print(f"Captions: {result.captions}  loudnorm: {result.loudnorm}")
    ai = result.ai_look or {}
    if ai:
        print(
            f"AI-look risk={ai.get('risk_score')} regenerate={ai.get('regenerate')} "
            f"notes={ai.get('notes')}"
        )
        if ai.get("regenerate"):
            print("Flagged for regenerate / human review (possible AI-look or frozen frames)")

    meta_path = Path(result.output).with_suffix(".json")
    meta_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    print(f"Meta → {meta_path}")
    print(json.dumps({"output": result.output, "regenerate": ai.get("regenerate", False)}))


if __name__ == "__main__":
    main()
