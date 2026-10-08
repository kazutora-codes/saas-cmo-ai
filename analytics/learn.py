"""Brick 9: extract durable learnings from outcomes and feed strategy/content."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analytics.store import init_db, list_posts
from core.config import ROOT, load_yaml


def load_learning_config() -> dict[str, Any]:
    path = ROOT / "config" / "learning.yaml"
    if path.exists():
        return load_yaml(path)
    return {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def learnings_path() -> Path:
    cfg = load_learning_config()
    rel = cfg.get("store", "data/analytics/learnings.json")
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_learnings() -> dict[str, Any]:
    path = learnings_path()
    if not path.exists():
        return _empty_learnings()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_learnings()


def _empty_learnings() -> dict[str, Any]:
    return {
        "updated_at": None,
        "rules_do": [],
        "rules_dont": [],
        "topic_boost": [],
        "topic_avoid": [],
        "winning_hooks": [],
        "losing_phrases": [],
        "stats": {},
        "notes": [],
    }


def save_learnings(data: dict[str, Any]) -> Path:
    data["updated_at"] = _now()
    path = learnings_path()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    cfg = load_learning_config()
    hist = ROOT / cfg.get("history_dir", "data/analytics/learning_runs")
    hist.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (hist / f"learnings_{stamp}.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    return path


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z]{3,}", (text or "").lower())


def _first_line(body: str) -> str:
    return (body or "").strip().split("\n")[0].strip()[:160]


def extract_learnings(use_llm: bool | None = None) -> dict[str, Any]:
    init_db()
    cfg = load_learning_config()
    if use_llm is None:
        use_llm = bool(cfg.get("use_llm", False))

    winners = list_posts(limit=50, label="winner")
    losers = list_posts(limit=50, label="loser")
    neutrals = [p for p in list_posts(limit=80) if p.get("label") == "neutral"]

    min_w = int(cfg.get("min_winners", 2))
    min_l = int(cfg.get("min_losers", 1))

    data = load_learnings()
    data["stats"] = {
        "winners": len(winners),
        "losers": len(losers),
        "neutrals": len(neutrals),
        "enough_signal": len(winners) >= min_w,
    }

    if len(winners) < min_w and len(losers) < min_l:
        data["notes"] = [
            "Not enough labeled outcomes yet - keep logging metrics after posts go live."
        ]
        return data

    rules_do: list[str] = []
    rules_dont: list[str] = []
    winning_hooks: list[str] = []
    losing_phrases: list[str] = []
    notes: list[str] = []

    win_bodies = [str(w.get("body") or "") for w in winners]
    lose_bodies = [str(l.get("body") or "") for l in losers]
    win_joined = " ".join(win_bodies).lower()
    lose_joined = " ".join(lose_bodies).lower()

    if any(x in win_joined for x in ("you ", "your ")):
        rules_do.append("Speak directly to the reader (you/your).")
    if any(x in win_joined for x in ("?", "stop ", "don't ", "delete")):
        rules_do.append("Use concrete challenges, questions, or deletes over announcements.")
    if any(x in win_joined for x in ("cool.", "nobody", "theater", "opened ")):
        rules_do.append("Prefer dry, specific sarcasm over hype.")

    avg_win_len = sum(len(b) for b in win_bodies) / max(len(win_bodies), 1)
    if avg_win_len and avg_win_len < 280:
        rules_do.append("Keep posts tight - winners average under ~280 chars of fluff.")

    fluff = [
        "excited to announce",
        "game-changer",
        "unlock the power",
        "thrilled",
        "synergy",
        "revolutionize",
        "in today's world",
    ]
    for phrase in fluff:
        if phrase in lose_joined:
            rules_dont.append(f'Avoid "{phrase}".')
            losing_phrases.append(phrase)

    if any(x in lose_joined for x in ("excited", "announce", "proud to")):
        rules_dont.append("No launch-theater language.")

    win_topics = [str(w.get("topic") or "").strip() for w in winners if w.get("topic")]
    lose_topics = [str(l.get("topic") or "").strip() for l in losers if l.get("topic")]
    topic_boost = list(dict.fromkeys(t for t in win_topics if t))[: int(cfg.get("max_topic_boosts", 8))]
    topic_avoid = list(
        dict.fromkeys(t for t in lose_topics if t and t not in topic_boost)
    )[: int(cfg.get("max_topic_avoid", 8))]

    for w in winners[:5]:
        hook = _first_line(str(w.get("body") or ""))
        if hook:
            winning_hooks.append(hook)

    win_counts = Counter(_tokens(" ".join(win_bodies)))
    lose_counts = Counter(_tokens(" ".join(lose_bodies)))
    stop = {
        "the", "and", "for", "that", "with", "your", "you", "this", "from",
        "have", "are", "was", "our", "not", "but", "all", "can", "has",
    }
    boost_words = []
    for word, c in win_counts.most_common(30):
        if word in stop or c < 2:
            continue
        if lose_counts.get(word, 0) == 0:
            boost_words.append(word)
        if len(boost_words) >= 6:
            break
    if boost_words:
        notes.append("Words skewed to winners: " + ", ".join(boost_words))

    max_rules = int(cfg.get("max_rules", 12))
    data["rules_do"] = list(dict.fromkeys(rules_do))[:max_rules]
    data["rules_dont"] = list(dict.fromkeys(rules_dont))[:max_rules]
    data["topic_boost"] = topic_boost
    data["topic_avoid"] = topic_avoid
    data["winning_hooks"] = list(dict.fromkeys(winning_hooks))[:8]
    data["losing_phrases"] = list(dict.fromkeys(losing_phrases))[:12]
    data["notes"] = notes or ["Heuristic patterns extracted from labeled outcomes."]

    if use_llm:
        data = _llm_refine_learnings(data, winners, losers)

    return data


def _llm_refine_learnings(
    data: dict[str, Any],
    winners: list[dict[str, Any]],
    losers: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        from core.llm import FreeLLM

        llm = FreeLLM()
        win_snip = "\n".join(f"- {w.get('body','')[:200]}" for w in winners[:5])
        lose_snip = "\n".join(f"- {l.get('body','')[:200]}" for l in losers[:5])
        system = (
            "You are a CMO reviewing post performance. "
            "Return STRICT JSON only with keys: rules_do, rules_dont, notes "
            "(each a list of short strings). No markdown."
        )
        user = (
            f"Winners:\n{win_snip}\n\nLosers:\n{lose_snip}\n\n"
            f"Current heuristic rules_do: {data.get('rules_do')}\n"
            f"rules_dont: {data.get('rules_dont')}"
        )
        resp = llm.chat(system, user)
        text = resp.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed = json.loads(text)
        if isinstance(parsed.get("rules_do"), list):
            data["rules_do"] = list(
                dict.fromkeys(data["rules_do"] + [str(x) for x in parsed["rules_do"]])
            )[:12]
        if isinstance(parsed.get("rules_dont"), list):
            data["rules_dont"] = list(
                dict.fromkeys(data["rules_dont"] + [str(x) for x in parsed["rules_dont"]])
            )[:12]
        if isinstance(parsed.get("notes"), list):
            data["notes"] = data.get("notes", []) + [str(x) for x in parsed["notes"][:3]]
        data["notes"].append(f"LLM refine via {resp.provider}/{resp.model}")
    except Exception as e:
        data.setdefault("notes", []).append(f"LLM refine skipped: {e}")
    return data


def learnings_prompt_block() -> str:
    data = load_learnings()
    if not data.get("updated_at") and not data.get("rules_do"):
        return ""
    lines = ["Learnings from real post outcomes (follow these):"]
    for r in data.get("rules_do") or []:
        lines.append(f"DO: {r}")
    for r in data.get("rules_dont") or []:
        lines.append(f"DON'T: {r}")
    if data.get("winning_hooks"):
        lines.append("Recent winning hooks:")
        for h in data["winning_hooks"][:4]:
            lines.append(f"- {h}")
    if data.get("topic_boost"):
        lines.append("Topics that worked: " + "; ".join(data["topic_boost"][:5]))
    if data.get("topic_avoid"):
        lines.append("Topics that underperformed: " + "; ".join(data["topic_avoid"][:5]))
    return "\n".join(lines) if len(lines) > 1 else ""


def run_learning_cycle(use_llm: bool | None = None) -> dict[str, Any]:
    data = extract_learnings(use_llm=use_llm)
    path = save_learnings(data)
    data["_path"] = str(path)
    return data
