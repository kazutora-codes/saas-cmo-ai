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

## Quick start

```bash
cd saas-cmo-ai
cp config/brand.example.yaml config/brand.yaml
pip install -r requirements.txt
# Optional free LLM: ollama pull llama3.2 && ollama serve
# Or set GROQ_API_KEY / GEMINI_API_KEY in .env

# Brick 2 — market intel (no keys)
python scripts/run_market_intel.py --no-llm

# Brick 3 — weekly pillars + calendar
python scripts/run_strategy.py --no-llm

# Brick 1+4 — content from strategy, ranked by quality gates
python scripts/generate_content.py --from-strategy 0 --with-intel --no-llm-judge
python scripts/rank_content.py data/content/<file>.json --no-llm

# Brick 5 — vertical short from a real clip (FFmpeg)
python scripts/process_video.py path/to/clip.mp4 -c "Your team opened 2 of 47 charts."

# Brick 6 — queue + publish (export without API keys)
python scripts/queue_post.py --body "Your dashboard has 47 charts." --platform x
python scripts/publish.py --force-export
python scripts/queue_post.py --list
```

## Philosophy

- Prefer local / free over paid.
- Every piece of content must pass intent + non-generic gates.
- Video: hybrid real footage first; pure AI video is high-risk and often rejected by the AI-look gate.
- Autopilot comes after the learning loop has real data — not before.
