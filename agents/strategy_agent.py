"""Brick 3: strategy agent - weekly pillars + post calendar from brand + intel."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.config import ROOT, load_brand, load_latest_intel, load_settings, load_yaml
from core.llm import FreeLLM


@dataclass
class Pillar:
    id: str
    name: str
    intent: str
    source: str = "default"


@dataclass
class PlannedPost:
    day_offset: int
    date: str
    platform: str
    pillar_id: str
    topic: str
    intent: str
    format: str
    notes: str = ""


@dataclass
class WeeklyPlan:
    generated_at: str
    week_start: str
    product: str
    pillars: list[Pillar] = field(default_factory=list)
    calendar: list[PlannedPost] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    llm_meta: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "week_start": self.week_start,
            "product": self.product,
            "pillars": [asdict(p) for p in self.pillars],
            "calendar": [asdict(c) for c in self.calendar],
            "themes": self.themes,
            "llm_meta": self.llm_meta,
        }


def load_strategy_config() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "strategy.yaml")


def _week_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _intel_topics(intel: dict[str, Any] | None) -> list[str]:
    if not intel:
        return []
    summary = intel.get("llm_summary") or {}
    topics: list[str] = []
    for key in ("recommended_topics", "opportunities", "fallback_topics"):
        for t in summary.get(key) or []:
            if t and t not in topics:
                topics.append(str(t))
    for a in intel.get("content_angles") or []:
        if a and a not in topics:
            topics.append(str(a))
    return topics


def _intel_themes(intel: dict[str, Any] | None) -> list[str]:
    if not intel:
        return []
    summary = intel.get("llm_summary") or {}
    themes = [str(t) for t in (summary.get("themes") or []) if t]
    if themes:
        return themes
    titles = [s.get("title", "") for s in (intel.get("top_signals") or [])[:8]]
    return [t for t in titles if t][:5]


def _default_pillars(cfg: dict[str, Any]) -> list[Pillar]:
    out: list[Pillar] = []
    for p in cfg.get("pillars", {}).get("defaults", []):
        out.append(
            Pillar(
                id=str(p["id"]),
                name=str(p["name"]),
                intent=str(p["intent"]),
                source="default",
            )
        )
    return out


def _merge_pillars(
    defaults: list[Pillar],
    themes: list[str],
    topics: list[str],
) -> list[Pillar]:
    pillars = list(defaults)
    brand_hint = "saas analytics product startup founder growth pricing onboarding"
    for i, theme in enumerate(themes):
        lower = theme.lower()
        if not any(w in lower for w in brand_hint.split()):
            continue
        pillars.append(
            Pillar(
                id=f"intel_{i+1}",
                name=theme[:80],
                intent=f"ride current market conversation: {theme[:120]}",
                source="intel",
            )
        )
        if sum(1 for p in pillars if p.source == "intel") >= 2:
            break
    return pillars[:6]


def _rule_calendar(
    cfg: dict[str, Any],
    brand: dict[str, Any],
    pillars: list[Pillar],
    topics: list[str],
    week_start: datetime,
) -> list[PlannedPost]:
    cadence = cfg.get("week", {}).get("cadence", {"x": 5, "linkedin": 3})
    formats = cfg.get("formats", {})
    max_posts = int(cfg.get("planning", {}).get("max_posts", 10))
    product = brand.get("product", {})
    stop = {
        "that", "does", "doesn't", "with", "from", "this", "your", "their",
        "need", "needs", "team", "teams", "more", "than", "have", "will",
        "into", "about", "just", "like", "when", "what", "which", "under",
    }
    brand_words = {
        w
        for w in re.findall(
            r"[a-z0-9]{4,}",
            " ".join(
                [
                    str(product.get("name", "")),
                    str(product.get("one_liner", "")),
                    str(product.get("audience", "")),
                    " ".join(product.get("differentiators", [])),
                    "saas analytics onboarding pricing churn growth dashboard metrics founder product",
                ]
            ).lower(),
        )
        if w not in stop
    }

    def _brand_fit(text: str) -> int:
        lower = text.lower()
        return sum(1 for w in brand_words if w in lower)

    fallback_topics = [
        f"Why {product.get('one_liner', 'this product')} beats dashboard theater",
        "Onboarding that ships in under 10 minutes - what we deleted",
        "Your team ignores the analytics tool. Here's the real reason.",
        "Pricing honesty as a growth lever",
        "Stop reporting vanity metrics to founders",
        "The feature request that should have been a no",
        "What plain-English insights actually means in the product",
        "Competitors sell complexity. We sell answers.",
    ]
    relevant = [t for t in topics if _brand_fit(t) >= 1]
    weak = [t for t in topics if _brand_fit(t) < 1]
    pool = relevant + fallback_topics + weak
    seen: set[str] = set()
    clean: list[str] = []
    for t in pool:
        key = re.sub(r"\W+", " ", t.lower()).strip()
        if key in seen or len(t) < 8:
            continue
        seen.add(key)
        clean.append(t)

    slots: list[tuple[str, int]] = []
    for platform, count in cadence.items():
        count = int(count)
        if count <= 0:
            continue
        step = max(1, 7 // count)
        for i in range(count):
            slots.append((platform, min(6, i * step)))
    slots.sort(key=lambda x: (x[1], x[0]))
    slots = slots[:max_posts]

    calendar: list[PlannedPost] = []
    for i, (platform, day_off) in enumerate(slots):
        pillar = pillars[i % len(pillars)] if pillars else Pillar("pain", "Pain", "pain")
        topic = clean[i % len(clean)] if clean else "SaaS growth without the fluff"
        fmt_list = formats.get(platform) or ["short_take"]
        fmt = fmt_list[i % len(fmt_list)]
        date = (week_start + timedelta(days=day_off)).date().isoformat()
        calendar.append(
            PlannedPost(
                day_offset=day_off,
                date=date,
                platform=platform,
                pillar_id=pillar.id,
                topic=topic,
                intent=pillar.intent,
                format=fmt,
                notes="rule-based",
            )
        )
    return calendar


def _llm_plan(
    brand: dict[str, Any],
    pillars: list[Pillar],
    themes: list[str],
    topics: list[str],
    cfg: dict[str, Any],
    week_start: datetime,
) -> tuple[list[Pillar], list[PlannedPost], dict[str, Any]] | None:
    product = brand.get("product", {})
    goals = brand.get("goals", {})
    cadence = cfg.get("week", {}).get("cadence", {})
    max_posts = int(cfg.get("planning", {}).get("max_posts", 10))

    system = (
        "You are a SaaS CMO. Produce a sharp weekly content strategy. "
        "Output STRICT JSON only. No generic marketing."
    )
    user = f"""Product: {product.get('name')} - {product.get('one_liner')}
Audience: {product.get('audience')}
Primary goal: {goals.get('primary')}
Voice: {brand.get('voice', {}).get('tone')}

Market themes: {themes[:6]}
Candidate topics: {topics[:10]}
Default pillars: {[p.name for p in pillars if p.source == 'default']}
Cadence targets: {cadence}
Week starts (UTC): {week_start.date().isoformat()}
Max posts: {max_posts}

Return JSON:
{{
  "pillars": [
    {{"id": "snake_case", "name": "short name", "intent": "why this pillar exists"}}
  ],
  "calendar": [
    {{
      "day_offset": 0,
      "platform": "x",
      "pillar_id": "pain",
      "topic": "specific post topic",
      "intent": "business outcome",
      "format": "short_take",
      "notes": "optional"
    }}
  ],
  "themes": ["refined weekly themes"]
}}
Rules: day_offset 0-6; platforms only x or linkedin; topics must be specific and non-generic.
"""
    try:
        resp = FreeLLM().chat(system, user)
        text = resp.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
    except Exception:
        return None

    llm_pillars: list[Pillar] = []
    for p in data.get("pillars") or []:
        llm_pillars.append(
            Pillar(
                id=str(p.get("id") or f"p{len(llm_pillars)}"),
                name=str(p.get("name") or "Pillar"),
                intent=str(p.get("intent") or ""),
                source="llm",
            )
        )
    if not llm_pillars:
        llm_pillars = pillars

    calendar: list[PlannedPost] = []
    for row in data.get("calendar") or []:
        try:
            day_off = int(row.get("day_offset", 0))
        except (TypeError, ValueError):
            day_off = 0
        day_off = max(0, min(6, day_off))
        platform = str(row.get("platform") or "x").lower()
        if platform not in ("x", "linkedin"):
            platform = "x"
        date = (week_start + timedelta(days=day_off)).date().isoformat()
        calendar.append(
            PlannedPost(
                day_offset=day_off,
                date=date,
                platform=platform,
                pillar_id=str(row.get("pillar_id") or "pain"),
                topic=str(row.get("topic") or "Untitled"),
                intent=str(row.get("intent") or ""),
                format=str(row.get("format") or "short_take"),
                notes=str(row.get("notes") or "llm"),
            )
        )
    calendar = calendar[:max_posts]
    meta = {
        "provider": resp.provider,
        "model": resp.model,
        "themes": data.get("themes") or themes,
    }
    return llm_pillars, calendar, meta


class StrategyAgent:
    def run(self, use_llm: bool | None = None) -> WeeklyPlan:
        cfg = load_strategy_config()
        brand = load_brand()
        intel = load_latest_intel()
        week_start = _week_start()
        themes = _intel_themes(intel)
        topics = _intel_topics(intel)
        pillars = _merge_pillars(_default_pillars(cfg), themes, topics)

        should_llm = cfg.get("planning", {}).get("use_llm", True) if use_llm is None else use_llm
        llm_meta = None
        calendar: list[PlannedPost]

        if should_llm:
            refined = _llm_plan(brand, pillars, themes, topics, cfg, week_start)
            if refined:
                pillars, calendar, llm_meta = refined
            else:
                calendar = _rule_calendar(cfg, brand, pillars, topics, week_start)
        else:
            calendar = _rule_calendar(cfg, brand, pillars, topics, week_start)

        return WeeklyPlan(
            generated_at=datetime.now(timezone.utc).isoformat(),
            week_start=week_start.date().isoformat(),
            product=str(brand.get("product", {}).get("name") or ""),
            pillars=pillars,
            calendar=calendar,
            themes=themes,
            llm_meta=llm_meta,
        )

    def save(self, plan: WeeklyPlan) -> Path:
        from core.config import ensure_data_dirs

        ensure_data_dirs()
        settings = load_settings()
        out_dir = ROOT / settings["paths"].get("strategy_out", "data/strategy")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"plan_{stamp}.json"
        payload = plan.to_dict()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (out_dir / "latest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
