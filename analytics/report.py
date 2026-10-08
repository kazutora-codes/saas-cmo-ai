"""Weekly what-worked / why report + few-shot export for content agent."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from analytics.store import (
    connect,
    evaluate_outcomes,
    init_db,
    load_analytics_config,
    losers,
    winners,
)
from core.config import ROOT


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_report(days: int | None = None) -> dict[str, Any]:
    init_db()
    evaluate_outcomes()
    cfg = load_analytics_config()
    days = days if days is not None else int(cfg.get("report", {}).get("default_days", 7))
    since = (_now() - timedelta(days=days)).isoformat()

    with connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM posts WHERE created_at >= ?", (since,)
        ).fetchone()["c"]
        by_label = conn.execute(
            """
            SELECT o.label, COUNT(*) AS c
            FROM outcomes o
            JOIN posts p ON p.id = o.post_id
            WHERE p.created_at >= ?
            GROUP BY o.label
            """,
            (since,),
        ).fetchall()
        by_platform = conn.execute(
            """
            SELECT platform, COUNT(*) AS c FROM posts
            WHERE created_at >= ?
            GROUP BY platform
            """,
            (since,),
        ).fetchall()
        top = conn.execute(
            """
            SELECT p.body, p.platform, p.topic, o.label, o.engagement_rate, o.reason,
                   m.likes, m.replies, m.reposts, m.impressions
            FROM posts p
            JOIN outcomes o ON o.post_id = p.id
            LEFT JOIN metrics m ON m.id = (
                SELECT id FROM metrics WHERE post_id = p.id ORDER BY recorded_at DESC LIMIT 1
            )
            WHERE p.created_at >= ? AND o.label = 'winner'
            ORDER BY COALESCE(o.engagement_rate, 0) DESC, m.likes DESC
            LIMIT 5
            """,
            (since,),
        ).fetchall()
        bottom = conn.execute(
            """
            SELECT p.body, p.platform, p.topic, o.label, o.engagement_rate, o.reason,
                   m.likes, m.impressions
            FROM posts p
            JOIN outcomes o ON o.post_id = p.id
            LEFT JOIN metrics m ON m.id = (
                SELECT id FROM metrics WHERE post_id = p.id ORDER BY recorded_at DESC LIMIT 1
            )
            WHERE p.created_at >= ? AND o.label = 'loser'
            ORDER BY m.likes ASC
            LIMIT 5
            """,
            (since,),
        ).fetchall()

    win_bodies = [r["body"] for r in top]
    lose_bodies = [r["body"] for r in bottom]

    why_winners = _pattern_notes(win_bodies, kind="winner")
    why_losers = _pattern_notes(lose_bodies, kind="loser")

    report = {
        "generated_at": _now().isoformat(),
        "window_days": days,
        "totals": {
            "posts": total,
            "by_label": {r["label"]: r["c"] for r in by_label},
            "by_platform": {r["platform"]: r["c"] for r in by_platform},
        },
        "winners": [dict(r) for r in top],
        "losers": [dict(r) for r in bottom],
        "why_winners": why_winners,
        "why_losers": why_losers,
        "few_shot": few_shot_examples(),
    }
    return report


def _pattern_notes(bodies: list[str], kind: str) -> list[str]:
    notes: list[str] = []
    if not bodies:
        return [f"No {kind}s in window yet - keep logging metrics."]
    joined = " ".join(bodies).lower()
    if kind == "winner":
        if any(x in joined for x in ("you ", "your ")):
            notes.append("Winners often speak directly to the reader (you/your).")
        if any(x in joined for x in ("?", "stop ", "delete")):
            notes.append("Specific challenges and questions correlate with winners.")
        if any(x in joined for x in ("cool.", "nobody", "deleted")):
            notes.append("Dry / specific sarcasm appears in winners.")
        if not notes:
            notes.append("Winners tend to be concrete and short.")
    else:
        if any(x in joined for x in ("excited", "game-changer", "unlock", "thrilled")):
            notes.append("Losers often contain generic marketing fluff.")
        if sum(len(b) for b in bodies) / max(len(bodies), 1) > 400:
            notes.append("Losers skew long / vague.")
        if not notes:
            notes.append("Losers lack a sharp specific claim.")
    return notes


def few_shot_examples() -> list[dict[str, str]]:
    cfg = load_analytics_config().get("learning", {})
    n = int(cfg.get("few_shot_top_n", 5))
    min_posts = int(cfg.get("min_posts", 3))
    wins = winners(limit=n)
    if len(wins) < 1:
        return []
    examples = []
    for w in wins:
        examples.append(
            {
                "platform": w.get("platform") or "x",
                "topic": w.get("topic") or "",
                "body": w.get("body") or "",
                "label": "winner",
            }
        )
    if len(wins) < min_posts:
        for ex in examples:
            ex["note"] = "thin_sample"
    return examples


def save_report(report: dict[str, Any] | None = None, days: int | None = None) -> Path:
    report = report or generate_report(days=days)
    out_dir = ROOT / "data" / "analytics"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"report_{stamp}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "latest_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "few_shot.json").write_text(
        json.dumps(report.get("few_shot") or [], indent=2), encoding="utf-8"
    )
    return path


def load_few_shot() -> list[dict[str, str]]:
    path = ROOT / "data" / "analytics" / "few_shot.json"
    if not path.exists():
        return few_shot_examples()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
