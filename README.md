# SaaS CMO AI (Free Stack)

Autonomous marketing agent for SaaS — built brick by brick, **$0 required**.

## Free stack (locked)

| Layer | Choice | Cost |
|--------|--------|------|
| Runtime | Python 3.12 | Free |
| LLM | Ollama (local) primary; Groq / Gemini free tiers optional | Free |
| Orchestration | Plain Python agents + YAML config | Free |
| Video edit | FFmpeg + Whisper.cpp / faster-whisper (local) | Free |
| Analytics | SQLite + simple reports | Free |
| Social APIs | Official free developer tiers only (rate-limited) | Free tier |
| Hosting | Your machine first; later Cloudflare / Fly free tiers | Free |

No paid APIs required to run the core loop. Optional free-tier keys go in `.env`.

## Bricks

1. **Foundation** — config, brand voice, free LLM client, content agent (text)
2. **Market intel** — free sources (HN, Reddit public, RSS, trends)
3. **Strategy agent** — weekly themes, pillars, post plan
4. **Quality gates** — anti-generic + humor/intent scoring
5. **Video pipeline** — FFmpeg captions, crops, AI-look heuristics
6. **Publish adapters** — X / LinkedIn free API paths (manual fallback)
7. **Analytics + learning** — SQLite performance log, pattern extraction
8. **Autopilot loop** — schedule, regenerate-on-fail, daily improve

## Quick start (Brick 1)

```bash
cd saas-cmo-ai
cp config/brand.example.yaml config/brand.yaml
# Optional: set GROQ_API_KEY or GEMINI_API_KEY in .env for cloud free tiers
# Or run Ollama locally: ollama pull llama3.2 && ollama serve

python scripts/generate_content.py --topic "why your SaaS onboarding is too polite"
```

## Philosophy

- Prefer local / free over paid.
- Every piece of content must pass intent + non-generic gates.
- Video: hybrid real footage first; pure AI video is high-risk and often rejected by the AI-look gate.
- Autopilot comes after the learning loop has real data — not before.
