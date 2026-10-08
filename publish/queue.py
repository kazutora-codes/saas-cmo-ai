"""Local publish queue (JSON file). Free, no external service required."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import ROOT, load_yaml


def load_publish_config() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "publish.yaml")


def queue_path() -> Path:
    cfg = load_publish_config()
    p = ROOT / cfg.get("queue", {}).get("path", "data/publish/queue.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def export_dir() -> Path:
    cfg = load_publish_config()
    d = ROOT / cfg.get("queue", {}).get("export_dir", "data/publish/export")
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class QueueItem:
    id: str
    platform: str
    body: str
    status: str = "pending"  # pending | exported | published | failed | skipped
    topic: str = ""
    source: str = ""  # content file path or strategy slot
    scheduled_for: str = ""  # ISO date optional
    media_path: str = ""
    created_at: str = ""
    updated_at: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> QueueItem:
        return cls(
            id=str(data.get("id") or uuid.uuid4()),
            platform=str(data.get("platform") or "x"),
            body=str(data.get("body") or ""),
            status=str(data.get("status") or "pending"),
            topic=str(data.get("topic") or ""),
            source=str(data.get("source") or ""),
            scheduled_for=str(data.get("scheduled_for") or ""),
            media_path=str(data.get("media_path") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            result=dict(data.get("result") or {}),
            notes=str(data.get("notes") or ""),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_queue() -> list[QueueItem]:
    path = queue_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("items", [])
    return [QueueItem.from_dict(i) for i in items]


def save_queue(items: list[QueueItem]) -> Path:
    path = queue_path()
    payload = {
        "updated_at": _now(),
        "items": [i.to_dict() for i in items],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def enqueue(
    body: str,
    platform: str = "x",
    topic: str = "",
    source: str = "",
    scheduled_for: str = "",
    media_path: str = "",
    notes: str = "",
) -> QueueItem:
    cfg = load_publish_config()
    platforms = cfg.get("platforms", {})
    if platform not in platforms:
        raise ValueError(f"Unknown platform: {platform}")
    max_chars = int(platforms[platform].get("max_chars", 280))
    body = body.strip()
    if len(body) > max_chars:
        notes = f"{notes}; truncated_from_{len(body)}".strip("; ")
        body = body[: max_chars - 1].rstrip() + "..."

    item = QueueItem(
        id=str(uuid.uuid4())[:8],
        platform=platform,
        body=body,
        status="pending",
        topic=topic,
        source=source,
        scheduled_for=scheduled_for,
        media_path=media_path,
        created_at=_now(),
        updated_at=_now(),
        notes=notes,
    )
    items = load_queue()
    items.append(item)
    save_queue(items)
    return item


def update_item(item_id: str, **fields: Any) -> QueueItem | None:
    items = load_queue()
    for i, item in enumerate(items):
        if item.id == item_id:
            data = item.to_dict()
            data.update(fields)
            data["updated_at"] = _now()
            items[i] = QueueItem.from_dict(data)
            save_queue(items)
            return items[i]
    return None


def pending_items(platform: str | None = None) -> list[QueueItem]:
    items = [i for i in load_queue() if i.status == "pending"]
    if platform:
        items = [i for i in items if i.platform == platform]
    return items
