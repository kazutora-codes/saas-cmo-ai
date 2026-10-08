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
    for key in ("data_dir", "content_out"):
        (ROOT / settings["paths"][key]).mkdir(parents=True, exist_ok=True)
