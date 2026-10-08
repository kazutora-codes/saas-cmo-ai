"""Free LLM client: Ollama local first, then free-tier cloud APIs via OpenAI-compatible HTTP."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import load_settings


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str


class FreeLLM:
    def __init__(self) -> None:
        self.settings = load_settings()["llm"]
        self.temperature = self.settings.get("temperature", 0.85)
        self.max_tokens = self.settings.get("max_tokens", 1200)

    def _providers(self) -> list[dict[str, Any]]:
        ready: list[dict[str, Any]] = []
        for p in self.settings["providers"]:
            env_name = p.get("api_key_env")
            if env_name is None:
                ready.append({**p, "api_key": "ollama"})
                continue
            key = os.getenv(env_name, "").strip()
            if key:
                ready.append({**p, "api_key": key})
        return ready

    def chat(self, system: str, user: str) -> LLMResponse:
        errors: list[str] = []
        for p in self._providers():
            try:
                return self._call(p, system, user)
            except Exception as e:  # noqa: BLE001 — try next free provider
                errors.append(f"{p['name']}: {e}")
        raise RuntimeError(
            "No free LLM available. Start Ollama (`ollama serve` + `ollama pull llama3.2`) "
            "or set GROQ_API_KEY / GEMINI_API_KEY in .env.\n"
            + "\n".join(errors)
        )

    def _call(self, provider: dict[str, Any], system: str, user: str) -> LLMResponse:
        url = provider["base_url"].rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": provider["model"],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=120.0) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        text = data["choices"][0]["message"]["content"].strip()
        return LLMResponse(text=text, provider=provider["name"], model=provider["model"])
