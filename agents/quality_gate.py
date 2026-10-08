"""Brick 4: quality gates - heuristic + LLM judge, variant ranking."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from core.config import ROOT, load_brand, load_settings, load_yaml
from core.llm import FreeLLM

FLUFF = [
    "game-changer",
    "unlock the power",
    "in today's world",
    "revolutionize",
    "seamless",
    "excited to announce",
    "thrilled to share",
    "synergy",
    "leverage our",
]

HUMOR_MARKERS = [
    "?",
    "...",
    "-",
    " - ",
    "nobody",
    "actually",
    "cool.",
    "sure.",
    "fine.",
    "lol",
    "honestly",
]


@dataclass
class QualityScore:
    intent: float
    originality: float
    humor: float
    brand_fit: float
    overall: float
    passed: bool
    notes: list[str] = field(default_factory=list)
    source: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_quality_config() -> dict[str, Any]:
    path = ROOT / "config" / "quality.yaml"
    if path.exists():
        return load_yaml(path)
    return {}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def heuristic_score(body: str, brand: dict[str, Any] | None = None) -> QualityScore:
    brand = brand or load_brand()
    cfg = load_quality_config()
    thresholds = cfg.get("thresholds", {})
    weights = cfg.get("weights", {})
    notes: list[str] = []
    lower = body.lower()
    voice = brand.get("voice", {})
    product = brand.get("product", {})

    originality = 0.85
    for phrase in voice.get("forbidden", []):
        if str(phrase).lower() in lower:
            originality -= 0.25
            notes.append(f"forbidden:{phrase}")
    for f in FLUFF:
        if f in lower:
            originality -= 0.12
            notes.append(f"fluff:{f}")
    originality = _clamp(originality)

    intent = 0.45
    if any(x in lower for x in ("you ", "your ", "stop ", "don't ", "if you're", "if you ")):
        intent += 0.2
    if len(body) > 40:
        intent += 0.1
    if "?" in body or any(x in lower for x in ("try", "see", "fix", "compare", "delete", "stop")):
        intent += 0.15
    if any(x in lower for x in ("we ", "our product", product.get("name", "").lower())):
        intent += 0.05
    intent = _clamp(intent)

    humor = 0.35
    for m in HUMOR_MARKERS:
        if m.lower() in lower:
            humor += 0.06
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if lines and sum(len(ln) for ln in lines) / max(len(lines), 1) < 90:
        humor += 0.1
    if voice.get("sarcasm_ok") and any(
        x in lower for x in ("cool product", "sure,", "nobody opened", "deleted half")
    ):
        humor += 0.15
    if any(x in lower for x in ("lmao", "!!!", "mind blown")):
        humor -= 0.2
        notes.append("tryhard_humor")
    humor = _clamp(humor)

    brand_tokens = set(
        re.findall(
            r"[a-z0-9]{4,}",
            " ".join(
                [
                    str(product.get("name", "")),
                    str(product.get("one_liner", "")),
                    str(product.get("audience", "")),
                    " ".join(product.get("differentiators", [])),
                    "saas analytics onboarding pricing dashboard metrics founder growth",
                ]
            ).lower(),
        )
    )
    hits = sum(1 for t in brand_tokens if t in lower)
    brand_fit = _clamp(0.25 + hits * 0.12)
    if hits == 0:
        notes.append("weak_brand_fit")

    overall = (
        intent * float(weights.get("intent", 0.3))
        + originality * float(weights.get("originality", 0.25))
        + humor * float(weights.get("humor", 0.2))
        + brand_fit * float(weights.get("brand_fit", 0.25))
    )
    overall = _clamp(overall)

    passed = (
        intent >= float(thresholds.get("min_intent", 0.7))
        and originality >= float(thresholds.get("min_originality", 0.65))
        and brand_fit >= float(thresholds.get("min_brand_fit", 0.55))
        and overall >= float(thresholds.get("min_overall", 0.68))
    )
    if humor < float(thresholds.get("min_humor", 0.45)) and overall < 0.75:
        notes.append("low_humor")

    if not notes:
        notes.append("ok")

    return QualityScore(
        intent=round(intent, 2),
        originality=round(originality, 2),
        humor=round(humor, 2),
        brand_fit=round(brand_fit, 2),
        overall=round(overall, 2),
        passed=passed,
        notes=notes,
        source="heuristic",
    )


def llm_judge(body: str, brand: dict[str, Any] | None = None) -> QualityScore | None:
    brand = brand or load_brand()
    cfg = load_quality_config()
    thresholds = cfg.get("thresholds", {})
    product = brand.get("product", {})
    voice = brand.get("voice", {})

    system = (
        "You are a ruthless SaaS content quality judge. "
        "Score posts for a dry, sarcastic, non-corporate brand. "
        "Output STRICT JSON only."
    )
    user = f"""Brand: {product.get('name')} - {product.get('one_liner')}
Audience: {product.get('audience')}
Tone: {voice.get('tone')}
Humor level: {voice.get('humor_level')}
Sarcasm OK: {voice.get('sarcasm_ok')}
Good examples: {voice.get('good_examples')}
Bad examples: {voice.get('bad_examples')}

Post to judge:
\"\"\"
{body}
\"\"\"

Return JSON:
{{
  "intent": 0.0-1.0,
  "originality": 0.0-1.0,
  "humor": 0.0-1.0,
  "brand_fit": 0.0-1.0,
  "overall": 0.0-1.0,
  "notes": ["short reasons"],
  "verdict": "publish" or "reject"
}}
Rules: punish generic marketing, hype, and try-hard humor. Reward specificity and dry wit.
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

    overall = float(data.get("overall", 0.5))
    passed = overall >= float(thresholds.get("min_overall", 0.68)) and str(
        data.get("verdict", "")
    ).lower() in ("publish", "pass", "yes", "")
    notes = data.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]
    notes = [str(n) for n in notes]
    notes.append(f"llm:{getattr(resp, 'provider', '?')}")

    return QualityScore(
        intent=round(float(data.get("intent", 0.5)), 2),
        originality=round(float(data.get("originality", 0.5)), 2),
        humor=round(float(data.get("humor", 0.5)), 2),
        brand_fit=round(float(data.get("brand_fit", 0.5)), 2),
        overall=round(overall, 2),
        passed=passed,
        notes=notes,
        source="llm",
    )


def score_content(
    body: str,
    brand: dict[str, Any] | None = None,
    use_llm: bool | None = None,
) -> QualityScore:
    brand = brand or load_brand()
    cfg = load_quality_config()
    heur = heuristic_score(body, brand)

    should_llm = cfg.get("judge", {}).get("use_llm", True) if use_llm is None else use_llm
    if not should_llm:
        return heur

    judged = llm_judge(body, brand)
    if judged is None:
        heur.notes = list(heur.notes) + ["llm_unavailable"]
        return heur

    intent = min(heur.intent, judged.intent + 0.1)
    originality = min(heur.originality, judged.originality + 0.05)
    humor = heur.humor * 0.4 + judged.humor * 0.6
    brand_fit = heur.brand_fit * 0.4 + judged.brand_fit * 0.6
    weights = cfg.get("weights", {})
    overall = (
        intent * float(weights.get("intent", 0.3))
        + originality * float(weights.get("originality", 0.25))
        + humor * float(weights.get("humor", 0.2))
        + brand_fit * float(weights.get("brand_fit", 0.25))
    )
    thresholds = cfg.get("thresholds", {})
    passed = overall >= float(thresholds.get("min_overall", 0.68)) and judged.passed
    notes = list(dict.fromkeys(list(heur.notes) + list(judged.notes)))
    return QualityScore(
        intent=round(_clamp(intent), 2),
        originality=round(_clamp(originality), 2),
        humor=round(_clamp(humor), 2),
        brand_fit=round(_clamp(brand_fit), 2),
        overall=round(_clamp(overall), 2),
        passed=passed,
        notes=notes,
        source="blended",
    )


def rank_variants(
    pieces: list[dict[str, Any]],
    use_llm: bool | None = None,
) -> list[dict[str, Any]]:
    cfg = load_quality_config()
    brand = load_brand()
    ranked: list[dict[str, Any]] = []
    for i, piece in enumerate(pieces):
        body = str(piece.get("body") or "")
        q = score_content(body, brand=brand, use_llm=use_llm)
        row = dict(piece)
        row["quality"] = q.to_dict()
        row["variant_index"] = i
        ranked.append(row)

    if cfg.get("ranking", {}).get("drop_failures", True):
        survivors = [r for r in ranked if r["quality"]["passed"]]
        if survivors:
            ranked = survivors

    ranked.sort(key=lambda r: r["quality"]["overall"], reverse=True)
    for i, r in enumerate(ranked):
        r["rank"] = i + 1
    return ranked


def pick_winner(
    pieces: list[dict[str, Any]],
    use_llm: bool | None = None,
) -> dict[str, Any] | None:
    ranked = rank_variants(pieces, use_llm=use_llm)
    top_k = int(load_quality_config().get("ranking", {}).get("top_k", 1))
    if not ranked:
        return None
    return ranked[0] if top_k >= 1 else None
