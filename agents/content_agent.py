"""Brick 1: high-intent text content agent with anti-generic gates."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from core.config import load_brand, load_settings
from core.llm import FreeLLM


@dataclass
class ContentPiece:
    platform: str
    body: str
    hook: str
    intent: str
    cta: str
    intent_score: float
    originality_score: float
    notes: str
    provider: str
    model: str

    @property
    def passed(self) -> bool:
        settings = load_settings()["content"]
        return (
            self.intent_score >= settings["min_intent_score"]
            and self.originality_score >= settings["min_originality_score"]
        )


SYSTEM_PROMPT = """You are the CMO of a SaaS product. You write social posts that actually work.

Rules:
- High intent: every post has a clear business purpose (curiosity → profile visit, pain → trial, take → share).
- Never generic marketing. No hype adjectives. No "excited to announce".
- Humor and sarcasm calibrated to the brand. Dry > try-hard.
- Platform-native: short punchy for X; slightly longer insight for LinkedIn.
- Specific > vague. Name the real pain.
- Output STRICT JSON only, no markdown fences.
"""


def _brand_block(brand: dict[str, Any]) -> str:
    p = brand["product"]
    v = brand["voice"]
    return f"""Product: {p['name']} — {p['one_liner']}
Audience: {p['audience']}
Differentiators: {', '.join(p.get('differentiators', []))}
Tone: {v['tone']}
Humor level: {v.get('humor_level', 'high')}
Sarcasm OK: {v.get('sarcasm_ok', True)}
Forbidden phrases: {', '.join(v.get('forbidden', []))}
Good examples:
- {chr(10).join('- ' + e for e in v.get('good_examples', []))}
Bad examples (never write like this):
- {chr(10).join('- ' + e for e in v.get('bad_examples', []))}
Primary goal: {brand['goals']['primary']}
"""


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _heuristic_scores(body: str, brand: dict[str, Any]) -> tuple[float, float, str]:
    """Cheap local gates so we don't burn LLM calls on obvious trash."""
    notes: list[str] = []
    forbidden = [f.lower() for f in brand["voice"].get("forbidden", [])]
    lower = body.lower()

    originality = 0.85
    for phrase in forbidden:
        if phrase in lower:
            originality -= 0.25
            notes.append(f"forbidden: {phrase}")

    fluff = ["game-changer", "unlock the power", "in today's world", "revolutionize", "seamless"]
    for f in fluff:
        if f in lower:
            originality -= 0.15
            notes.append(f"fluff: {f}")

    intent = 0.5
    if any(x in lower for x in ("you ", "your ", "stop ", "don't ", "if you're")):
        intent += 0.2
    if len(body) > 40:
        intent += 0.1
    if "?" in body or any(x in lower for x in ("try", "see", "fix", "compare")):
        intent += 0.15
    intent = min(1.0, intent)
    originality = max(0.0, min(1.0, originality))
    return intent, originality, "; ".join(notes) if notes else "ok"


class ContentAgent:
    def __init__(self, llm: FreeLLM | None = None) -> None:
        self.llm = llm or FreeLLM()
        self.brand = load_brand()
        self.settings = load_settings()["content"]

    def generate(
        self,
        topic: str,
        platform: str = "x",
        extra_context: str = "",
    ) -> list[ContentPiece]:
        attempts = self.settings["max_regenerate_attempts"]
        variants = self.settings["variants_per_topic"]
        pieces: list[ContentPiece] = []

        for i in range(variants):
            piece = self._one(topic, platform, extra_context, attempt=0)
            for attempt in range(1, attempts):
                if piece.passed:
                    break
                piece = self._one(
                    topic,
                    platform,
                    extra_context
                    + f"\nPrevious draft failed gates ({piece.notes}). "
                    "Rewrite sharper, more specific, less generic.",
                    attempt=attempt,
                )
            pieces.append(piece)
        return pieces

    def _one(
        self,
        topic: str,
        platform: str,
        extra_context: str,
        attempt: int,
    ) -> ContentPiece:
        user = f"""{_brand_block(self.brand)}

Topic / angle: {topic}
Platform: {platform}
Attempt: {attempt + 1}
{extra_context}

Return JSON with keys:
{{
  "hook": "first line that stops the scroll",
  "body": "full post text ready to publish",
  "intent": "what business outcome this aims for",
  "cta": "soft or hard call to action (can be empty if pure brand)",
  "intent_score": 0.0-1.0,
  "originality_score": 0.0-1.0,
  "notes": "brief self-critique"
}}
"""
        resp = self.llm.chat(SYSTEM_PROMPT, user)
        try:
            data = _parse_json(resp.text)
        except json.JSONDecodeError:
            data = {
                "hook": resp.text.split("\n")[0][:120],
                "body": resp.text,
                "intent": "unknown",
                "cta": "",
                "intent_score": 0.4,
                "originality_score": 0.4,
                "notes": "model did not return valid JSON",
            }

        h_intent, h_orig, h_notes = _heuristic_scores(str(data.get("body", "")), self.brand)
        intent_score = min(float(data.get("intent_score", 0.5)), h_intent + 0.2)
        originality_score = min(float(data.get("originality_score", 0.5)), h_orig + 0.1)
        notes = str(data.get("notes", ""))
        if h_notes != "ok":
            notes = f"{notes}; gate: {h_notes}".strip("; ")

        return ContentPiece(
            platform=platform,
            body=str(data.get("body", "")).strip(),
            hook=str(data.get("hook", "")).strip(),
            intent=str(data.get("intent", "")).strip(),
            cta=str(data.get("cta", "")).strip(),
            intent_score=round(intent_score, 2),
            originality_score=round(originality_score, 2),
            notes=notes,
            provider=resp.provider,
            model=resp.model,
        )

    def to_dict_list(self, pieces: list[ContentPiece]) -> list[dict[str, Any]]:
        return [asdict(p) | {"passed": p.passed} for p in pieces]
