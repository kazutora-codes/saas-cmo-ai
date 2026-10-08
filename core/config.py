from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings() -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    return load_yaml(ROOT / "config" / "settings.yaml")


def load_brand() -> dict[str, Any]:
    settings = load_settings()
    brand_path = ROOT / settings["paths"]["brand"]
    example = ROOT / "config" / "brand.example.yaml"
    if not brand_path.exists():
        return load_yaml(example)
    return load_yaml(brand_path)


def ensure_data_dirs() -> None:
    settings = load_settings()
    for key in ("data_dir", "content_out", "intel_out"):
        path_key = settings["paths"].get(key)
        if path_key:
            (ROOT / path_key).mkdir(parents=True, exist_ok=True)


def load_latest_intel() -> dict | None:
    """Return the latest market intel brief if present."""
    settings = load_settings()
    latest = ROOT / settings["paths"].get("intel_out", "data/intel") / "latest.json"
    if not latest.exists():
        return None
    import json

    return json.loads(latest.read_text(encoding="utf-8"))
