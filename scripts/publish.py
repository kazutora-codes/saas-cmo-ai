#!/usr/bin/env python3
"""Brick 6 CLI: process publish queue — API when keys exist, else manual export."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from publish.adapters import publish_item  # noqa: E402
from publish.queue import load_queue, pending_items, update_item  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish or export pending queue items")
    parser.add_argument(
        "--platform",
        default="",
        choices=["", "x", "linkedin"],
        help="Only process this platform",
    )
    parser.add_argument("--id", default="", help="Process a single queue item id")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be published without writing/exporting",
    )
    parser.add_argument(
        "--force-export",
        action="store_true",
        help="Skip API and always write export package",
    )
    args = parser.parse_args()

    if args.id:
        items = [i for i in load_queue() if i.id == args.id]
        if not items:
            print(f"No item {args.id}", file=sys.stderr)
            sys.exit(1)
    else:
        items = pending_items(args.platform or None)

    if not items:
        print("No pending items.")
        return

    print(f"Processing {len(items)} item(s)…")
    for item in items:
        print(f"\n→ {item.id} [{item.platform}] {item.body[:80].replace(chr(10), ' ')}")
        if args.dry_run:
            print("  (dry-run)")
            continue

        if args.force_export:
            from publish.adapters import export_item

            result = export_item(item)
        else:
            result = publish_item(item)

        status = "published" if result.ok and result.mode == "api" else (
            "exported" if result.ok and result.mode == "export" else "failed"
        )
        update_item(
            item.id,
            status=status,
            result={
                "mode": result.mode,
                "message": result.message,
                "external_id": result.external_id,
                "export_path": result.export_path,
            },
            notes=result.message,
        )
        print(f"  {status}: {result.message}")
        if result.export_path:
            print(f"  files: {result.export_path}")
        if result.external_id:
            print(f"  external_id: {result.external_id}")

    print(f"\n{json.dumps({'processed': len(items)})}")


if __name__ == "__main__":
    main()
