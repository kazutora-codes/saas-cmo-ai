"""SQLite store: posts -> metrics -> outcomes. Free, local."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.config import ROOT, load_settings, load_yaml


def load_analytics_config() -> dict[str, Any]:
    path = ROOT / "config" / "analytics.yaml"
    if path.exists():
        return load_yaml(path)
    return {}


def db_path() -> Path:
    env = os.getenv("SAAS_CMO_ANALYTICS_DB", "").strip()
    if env:
        p = Path(env)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    cfg = load_analytics_config()
    rel = cfg.get("db") or load_settings().get("paths", {}).get(
        "analytics_db", "data/analytics/metrics.db"
    )
    p = Path(rel)
    if not p.is_absolute():
        p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    conn = sqlite3.connect(str(path), timeout=60.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    queue_id TEXT,
    platform TEXT NOT NULL,
    body TEXT NOT NULL,
    topic TEXT,
    source TEXT,
    published_at TEXT,
    external_id TEXT,
    quality_json TEXT,
    created_at TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    impressions INTEGER DEFAULT 0,
    likes INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    reposts INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    raw_json TEXT
)""",
    """CREATE TABLE IF NOT EXISTS outcomes (
    post_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    engagement_rate REAL,
    reason TEXT,
    evaluated_at TEXT NOT NULL
)""",
    "CREATE INDEX IF NOT EXISTS idx_posts_platform ON posts(platform)",
    "CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(published_at)",
    "CREATE INDEX IF NOT EXISTS idx_outcomes_label ON outcomes(label)",
]


def _ensure_schema(conn: sqlite3.Connection) -> None:
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)


def init_db() -> Path:
    with connect() as conn:
        _ensure_schema(conn)
    return db_path()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PostRecord:
    id: int
    platform: str
    body: str
    topic: str = ""
    queue_id: str = ""
    source: str = ""
    published_at: str = ""
    external_id: str = ""
    quality_json: str = ""


def log_post(
    body: str,
    platform: str,
    topic: str = "",
    queue_id: str = "",
    source: str = "",
    published_at: str = "",
    external_id: str = "",
    quality: dict[str, Any] | None = None,
) -> int:
    with connect() as conn:
        _ensure_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO posts (queue_id, platform, body, topic, source, published_at, external_id, quality_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                queue_id,
                platform,
                body,
                topic,
                source,
                published_at or _now(),
                external_id,
                json.dumps(quality or {}),
                _now(),
            ),
        )
        return int(cur.lastrowid)


def log_metrics(
    post_id: int,
    *,
    impressions: int = 0,
    likes: int = 0,
    replies: int = 0,
    reposts: int = 0,
    clicks: int = 0,
    raw: dict[str, Any] | None = None,
) -> int:
    with connect() as conn:
        _ensure_schema(conn)
        cur = conn.execute(
            """
            INSERT INTO metrics (post_id, recorded_at, impressions, likes, replies, reposts, clicks, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_id,
                _now(),
                impressions,
                likes,
                replies,
                reposts,
                clicks,
                json.dumps(raw or {}),
            ),
        )
        return int(cur.lastrowid)


def latest_metrics(post_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM metrics WHERE post_id = ? ORDER BY recorded_at DESC LIMIT 1",
            (post_id,),
        ).fetchone()
    return dict(row) if row else None


def evaluate_outcomes() -> int:
    cfg = load_analytics_config().get("outcome", {})
    win_eng = float(cfg.get("winner_min_engagement", 0.02))
    win_likes = int(cfg.get("winner_min_likes", 10))
    lose_likes = int(cfg.get("loser_max_likes", 2))
    updated = 0
    with connect() as conn:
        _ensure_schema(conn)
        posts = conn.execute("SELECT id FROM posts").fetchall()
        for p in posts:
            pid = int(p["id"])
            m = conn.execute(
                "SELECT * FROM metrics WHERE post_id = ? ORDER BY recorded_at DESC LIMIT 1",
                (pid,),
            ).fetchone()
            if not m:
                continue
            likes = int(m["likes"] or 0)
            replies = int(m["replies"] or 0)
            reposts = int(m["reposts"] or 0)
            impressions = int(m["impressions"] or 0)
            eng = None
            if impressions > 0:
                eng = (likes + replies + reposts) / impressions
            if eng is not None and eng >= win_eng:
                label, reason = "winner", f"engagement_rate={eng:.4f}"
            elif likes >= win_likes:
                label, reason = "winner", f"likes={likes}"
            elif likes <= lose_likes and impressions >= 50:
                label, reason = "loser", f"likes={likes} impressions={impressions}"
            elif likes <= lose_likes and eng is not None and eng < 0.005:
                label, reason = "loser", f"low_engagement={eng:.4f}"
            else:
                label, reason = "neutral", f"likes={likes}"
            conn.execute(
                """
                INSERT INTO outcomes (post_id, label, engagement_rate, reason, evaluated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(post_id) DO UPDATE SET
                    label=excluded.label,
                    engagement_rate=excluded.engagement_rate,
                    reason=excluded.reason,
                    evaluated_at=excluded.evaluated_at
                """,
                (pid, label, eng, reason, _now()),
            )
            updated += 1
    return updated


def list_posts(limit: int = 50, label: str | None = None) -> list[dict[str, Any]]:
    with connect() as conn:
        _ensure_schema(conn)
        if label:
            rows = conn.execute(
                """
                SELECT p.*, o.label, o.engagement_rate, o.reason
                FROM posts p
                JOIN outcomes o ON o.post_id = p.id
                WHERE o.label = ?
                ORDER BY p.created_at DESC LIMIT ?
                """,
                (label, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT p.*, o.label, o.engagement_rate, o.reason
                FROM posts p
                LEFT JOIN outcomes o ON o.post_id = p.id
                ORDER BY p.created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def winners(limit: int = 5) -> list[dict[str, Any]]:
    return list_posts(limit=limit, label="winner")


def losers(limit: int = 5) -> list[dict[str, Any]]:
    return list_posts(limit=limit, label="loser")


def import_from_queue() -> int:
    from publish.queue import load_queue

    items = load_queue()
    count = 0
    with connect() as conn:
        _ensure_schema(conn)
        for item in items:
            if item.status not in ("exported", "published"):
                continue
            exists = conn.execute(
                "SELECT id FROM posts WHERE queue_id = ?", (item.id,)
            ).fetchone()
            if exists:
                continue
            quality = item.result or {}
            conn.execute(
                """
                INSERT INTO posts (queue_id, platform, body, topic, source, published_at, external_id, quality_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.platform,
                    item.body,
                    item.topic,
                    item.source,
                    item.updated_at or item.created_at,
                    (item.result or {}).get("external_id", ""),
                    json.dumps(quality),
                    _now(),
                ),
            )
            count += 1
    return count
