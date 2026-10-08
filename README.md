# SaaS CMO AI (Free Stack)

Autonomous marketing agent for SaaS — built brick by brick, **$0 required**.

## Free stack (locked)

| Layer | Choice | Cost |
|--------|--------|------|
| Runtime | Python 3.12 | Free |
| LLM | Ollama (local) primary; Groq / Gemini free tiers optional | Free |
| Orchestration | Plain Python agents + YAML config | Free |
| Video edit | FFmpeg (local) | Free |
| Analytics | SQLite + learning rules | Free |
| Social APIs | Official free developer tiers only | Free tier |

## Bricks

1. **Foundation** — config, brand voice, free LLM client, content agent
2. **Market intel** — HN, Lobsters, Reddit, RSS
3. **Strategy agent** — weekly themes, pillars, post plan
4. **Quality gates** — anti-generic + humor/intent scoring
5. **Video pipeline** — FFmpeg captions, crops, AI-look heuristics
6. **Publish adapters** — X / LinkedIn free paths + manual export
7. **Analytics** — SQLite performance log, few-shot winners
8. **Autopilot loop** — schedule, regenerate-on-fail, kill switch
9. **Learning loop** — why winners win, feed rules back into content/strategy

## Quick start

```bash
cd saas-cmo-ai
cp config/brand.example.yaml config/brand.yaml
pip install -r requirements.txt
# Optional: ollama pull llama3.2 && ollama serve
# Or set GROQ_API_KEY / GEMINI_API_KEY in .env

python scripts/run_market_intel.py --no-llm
python scripts/run_strategy.py --no-llm
python scripts/generate_content.py --from-strategy 0 --with-intel --no-llm-judge
python scripts/queue_post.py --body "Your dashboard has 47 charts." --platform x
python scripts/publish.py --force-export
python scripts/log_metrics.py --init --import-queue
python scripts/analytics_report.py --days 7
python scripts/run_learning.py --import-queue
python scripts/run_autopilot.py --once
python scripts/run_learning.py --show
```

## Philosophy

- Prefer local / free over paid.
- Every piece of content must pass intent + non-generic gates.
- Video: hybrid real footage first.
- Autopilot improves daily from real outcome data.
