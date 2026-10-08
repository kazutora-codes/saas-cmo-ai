"""Brick 2: free market intelligence - HN, Lobsters, Reddit, RSS."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from core.config import ROOT, load_brand, load_settings, load_yaml
from core.llm import FreeLLM

USER_AGENT = "saas-cmo-ai/0.2 (+https://github.com/kazutora-codes/saas-cmo-ai; market-intel)"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
}


@dataclass
class Signal:
    source: str
    title: str
    url: str
    score: float
    relevance: float
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    published_at: str | None = None

    @property
    def rank(self) -> float:
        return self.score * 0.4 + self.relevance * 100 * 0.6


def load_intel_config() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "intel.yaml")


def _keywords(cfg: dict[str, Any]) -> list[str]:
    brand = load_brand()
    words: list[str] = list(cfg.get("keywords", {}).get("boost", []))
    product = brand.get("product", {})
    words.append(str(product.get("name", "")).lower())
    for d in product.get("differentiators", []):
        words.extend(re.findall(r"[a-z0-9]{4,}", d.lower()))
    for c in product.get("competitors", []):
        words.append(str(c).lower())
    audience = str(product.get("audience", "")).lower()
    words.extend(re.findall(r"[a-z0-9]{4,}", audience))
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        w = w.strip().lower()
        if len(w) < 3 or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def _relevance(text: str, keywords: list[str]) -> float:
    lower = text.lower()
    if not keywords:
        return 0.2
    hits = sum(1 for k in keywords if k in lower)
    return min(1.0, 0.15 + hits * 0.18)


def _client() -> httpx.Client:
    return httpx.Client(timeout=25.0, headers=HEADERS, follow_redirects=True)


def collect_hacker_news(cfg: dict[str, Any], keywords: list[str]) -> list[Signal]:
    section = cfg.get("hacker_news", {})
    if not section.get("enabled", True):
        return []
    top_n = int(section.get("top_n", 40))
    min_score = float(section.get("min_score", 30))
    signals: list[Signal] = []
    with _client() as client:
        ids = client.get("https://hacker-news.firebaseio.com/v0/topstories.json").json()
        for item_id in ids[:top_n]:
            try:
                item = client.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
                ).json()
            except Exception:
                continue
            if not item or item.get("type") != "story":
                continue
            score = float(item.get("score") or 0)
            if score < min_score:
                continue
            title = item.get("title") or ""
            url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
            text = f"{title} {item.get('text') or ''}"
            signals.append(
                Signal(
                    source="hacker_news",
                    title=title,
                    url=url,
                    score=score,
                    relevance=_relevance(text, keywords),
                    summary=(item.get("text") or "")[:280],
                    published_at=_unix_to_iso(item.get("time")),
                )
            )
    return signals


def collect_lobsters(cfg: dict[str, Any], keywords: list[str]) -> list[Signal]:
    section = cfg.get("lobsters", {})
    if not section.get("enabled", True):
        return []
    top_n = int(section.get("top_n", 30))
    min_score = float(section.get("min_score", 5))
    signals: list[Signal] = []
    with _client() as client:
        try:
            rows = client.get("https://lobste.rs/hottest.json").json()
        except Exception:
            return []
    for row in rows[:top_n]:
        score = float(row.get("score") or 0)
        if score < min_score:
            continue
        title = row.get("title") or ""
        tags = list(row.get("tags") or [])
        text = f"{title} {' '.join(tags)}"
        signals.append(
            Signal(
                source="lobsters",
                title=title,
                url=row.get("url") or row.get("short_id_url") or "",
                score=score,
                relevance=_relevance(text, keywords),
                tags=tags,
                published_at=row.get("created_at"),
            )
        )
    return signals


def collect_reddit(cfg: dict[str, Any], keywords: list[str]) -> list[Signal]:
    section = cfg.get("reddit", {})
    if not section.get("enabled", True):
        return []
    limit = int(section.get("limit_per_sub", 15))
    min_score = float(section.get("min_score", 20))
    signals: list[Signal] = []
    with _client() as client:
        for sub in section.get("subreddits", []):
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit}"
            try:
                r = client.get(url)
                if r.status_code != 200:
                    continue
                children = r.json().get("data", {}).get("children", [])
            except Exception:
                continue
            for child in children:
                d = child.get("data") or {}
                score = float(d.get("score") or 0)
                if score < min_score or d.get("stickied"):
                    continue
                title = d.get("title") or ""
                selftext = d.get("selftext") or ""
                text = f"{title} {selftext}"
                signals.append(
                    Signal(
                        source=f"reddit/r/{sub}",
                        title=title,
                        url=f"https://www.reddit.com{d.get('permalink', '')}",
                        score=score,
                        relevance=_relevance(text, keywords),
                        summary=selftext[:280],
                        published_at=_unix_to_iso(d.get("created_utc")),
                    )
                )
    return signals


def collect_rss(cfg: dict[str, Any], keywords: list[str]) -> list[Signal]:
    section = cfg.get("rss", {})
    if not section.get("enabled", True):
        return []
    max_items = int(section.get("max_items_per_feed", 12))
    signals: list[Signal] = []
    with _client() as client:
        for feed in section.get("feeds", []):
            name = feed.get("name") or urlparse(feed.get("url", "")).netloc
            try:
                r = client.get(feed["url"])
                r.raise_for_status()
                items = _parse_feed(r.text)
            except Exception:
                continue
            for item in items[:max_items]:
                title = item.get("title") or ""
                summary = item.get("summary") or ""
                text = f"{title} {summary}"
                signals.append(
                    Signal(
                        source=f"rss/{name}",
                        title=title,
                        url=item.get("url") or "",
                        score=10.0,
                        relevance=_relevance(text, keywords),
                        summary=summary[:280],
                        published_at=item.get("published_at"),
                    )
                )
    return signals


def _parse_feed(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    items: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc = (item.findtext("description") or "").strip()
        pub = item.findtext("pubDate")
        items.append(
            {
                "title": _strip_html(title),
                "url": link,
                "summary": _strip_html(desc),
                "published_at": _parse_date(pub),
            }
        )
    if not items:
        for entry in root.findall(".//entry"):
            title = (entry.findtext("title") or "").strip()
            link_el = entry.find("link")
            href = ""
            if link_el is not None:
                href = link_el.get("href") or (link_el.text or "")
            summary = (entry.findtext("summary") or entry.findtext("content") or "").strip()
            pub = entry.findtext("published") or entry.findtext("updated")
            items.append(
                {
                    "title": _strip_html(title),
                    "url": href.strip(),
                    "summary": _strip_html(summary),
                    "published_at": _parse_date(pub),
                }
            )
    return items


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        return value


def _unix_to_iso(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    except Exception:
        return None


def gather_signals(cfg: dict[str, Any] | None = None) -> list[Signal]:
    cfg = cfg or load_intel_config()
    keywords = _keywords(cfg)
    signals: list[Signal] = []
    signals.extend(collect_hacker_news(cfg, keywords))
    signals.extend(collect_lobsters(cfg, keywords))
    signals.extend(collect_reddit(cfg, keywords))
    signals.extend(collect_rss(cfg, keywords))
    seen: set[str] = set()
    unique: list[Signal] = []
    for s in sorted(signals, key=lambda x: x.rank, reverse=True):
        key = re.sub(r"\W+", " ", s.title.lower()).strip()[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return unique


def build_brief(
    signals: list[Signal],
    cfg: dict[str, Any] | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    cfg = cfg or load_intel_config()
    brief_cfg = cfg.get("brief", {})
    top_n = int(brief_cfg.get("top_signals", 15))
    n_angles = int(brief_cfg.get("content_angles", 8))
    top = signals[:top_n]
    brand = load_brand()
    angles: list[str] = []
    for s in top:
        if s.relevance < 0.25:
            continue
        angles.append(s.title)
        if len(angles) >= n_angles:
            break
    if len(angles) < n_angles:
        for s in top:
            if s.title in angles:
                continue
            angles.append(s.title)
            if len(angles) >= n_angles:
                break
    brief: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "product": brand.get("product", {}).get("name"),
        "signal_count": len(signals),
        "top_signals": [asdict(s) for s in top],
        "content_angles": angles,
        "source_breakdown": _source_breakdown(signals),
        "llm_summary": None,
    }
    should_llm = brief_cfg.get("use_llm", True) if use_llm is None else use_llm
    if should_llm and top:
        brief["llm_summary"] = _llm_refine(top, angles, brand)
    return brief


def _source_breakdown(signals: list[Signal]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in signals:
        key = s.source.split("/")[0]
        counts[key] = counts.get(key, 0) + 1
    return counts


def _llm_refine(
    top: list[Signal],
    angles: list[str],
    brand: dict[str, Any],
) -> dict[str, Any] | None:
    product = brand.get("product", {})
    lines = "\n".join(
        f"- [{s.source}] (rel={s.relevance:.2f}, score={s.score:.0f}) {s.title}"
        for s in top[:12]
    )
    system = (
        "You are a SaaS CMO research analyst. Output STRICT JSON only. "
        "Be concrete. No generic marketing advice."
    )
    user = f"""Product: {product.get('name')} - {product.get('one_liner')}
Audience: {product.get('audience')}

Today's ranked market signals:
{lines}

Return JSON:
{{
  "themes": ["3-5 short themes in the market right now"],
  "opportunities": ["3-5 content opportunities for this product"],
  "avoid": ["1-3 angles that are noisy or off-brand"],
  "recommended_topics": ["5 ready-to-use post topics, sharp and specific"]
}}
"""
    try:
        resp = FreeLLM().chat(system, user)
        text = resp.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        data = json.loads(text)
        data["_provider"] = resp.provider
        data["_model"] = resp.model
        return data
    except Exception as e:
        return {"error": str(e), "fallback_topics": angles[:5]}


class MarketIntelAgent:
    def run(self, use_llm: bool | None = None) -> dict[str, Any]:
        cfg = load_intel_config()
        signals = gather_signals(cfg)
        brief = build_brief(signals, cfg, use_llm=use_llm)
        return brief

    def save(self, brief: dict[str, Any]) -> Path:
        from core.config import ensure_data_dirs

        ensure_data_dirs()
        settings = load_settings()
        out_dir = ROOT / settings["paths"].get("intel_out", "data/intel")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"brief_{stamp}.json"
        path.write_text(json.dumps(brief, indent=2), encoding="utf-8")
        latest = out_dir / "latest.json"
        latest.write_text(json.dumps(brief, indent=2), encoding="utf-8")
        return path
