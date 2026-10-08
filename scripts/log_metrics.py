#!/usr/bin/env python3
"""Brick 7 CLI: log a post and/or metrics into the analytics SQLite DB."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.store import (  # noqa: E402
    evaluate_outcomes,
    import_from_queue,
    init_db,
    list_posts,
    log_metrics,
    log_post,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Log posts and engagement metrics")
    parser.add_argument("--init", action="store_true", help="Create SQLite schema")
    parser.add_argument("--import-queue", action="store_true", help="Import exported/published queue items")
    parser.add_argument("--body", default="", help="Post body (new post)")
    parser.add_argument("--platform", default="x", choices=["x", "linkedin"])
    parser.add_argument("--topic", default="")
    parser.add_argument("--post-id", type=int, default=0, help="Existing post id for metrics")
    parser.add_argument("--impressions", type=int, default=0)
    parser.add_argument("--likes", type=int, default=0)
    parser.add_argument("--replies", type=int, default=0)
    parser.add_argument("--reposts", type=int, default=0)
    parser.add_argument("--clicks", type=int, default=0)
    parser.add_argument("--evaluate", action="store_true", help="Recompute winner/loser labels")
    parser.add_argument("--list", action="store_true", help="List recent posts")
    args = parser.parse_args()

    if args.init:
        path = init_db()
        print(f"DB ready → {path}")

    if args.import_queue:
        n = import_from_queue()
        print(f"Imported {n} posts from publish queue")

    post_id = args.post_id
    if args.body:
        post_id = log_post(body=args.body, platform=args.platform, topic=args.topic)
        print(f"Logged post id={post_id}")

    if post_id and any(
        [args.impressions, args.likes, args.replies, args.reposts, args.clicks]
    ):
        mid = log_metrics(
            post_id,
            impressions=args.impressions,
            likes=args.likes,
            replies=args.replies,
            reposts=args.reposts,
            clicks=args.clicks,
        )
        print(f"Logged metrics id={mid} for post {post_id}")

    if args.evaluate:
        n = evaluate_outcomes()
        print(f"Evaluated outcomes for {n} posts with metrics")

    if args.list:
        for p in list_posts(limit=20):
            label = p.get("label") or "-"
            print(
                f"  #{p['id']} [{label:7}] {p['platform']:8} "
                f"eng={p.get('engagement_rate')}  {str(p['body'])[:60]}"
            )

    if not any(
        [args.init, args.import_queue, args.body, args.post_id, args.evaluate, args.list]
    ):
        parser.print_help()


if __name__ == "__main__":
    main()
