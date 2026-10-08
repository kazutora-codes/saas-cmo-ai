# Build log — brick by brick

## Brick 1 — Foundation (done)

- [x] Project layout
- [x] Brand voice YAML
- [x] Free LLM client (Ollama → Groq → Gemini)
- [x] Content agent with intent + originality gates
- [x] CLI: `scripts/generate_content.py`

**You need:** Ollama running locally, **or** a free Groq/Gemini API key in `.env`.

## Brick 2 — Market intel (next)

- Free RSS + Hacker News + Reddit public JSON
- Daily trend brief → feeds content agent

## Brick 3 — Strategy agent

- Weekly content pillars from intel + goals
- Calendar of planned posts

## Brick 4 — Stronger quality gates

- LLM-as-judge for humor calibration
- A/B variant ranking before publish

## Brick 5 — Video pipeline

- FFmpeg captions, 9:16 crop, loudnorm
- Simple AI-look heuristics + regenerate flag
- Script → captioned short from screen recording / stills

## Brick 6 — Publish adapters

- X API free tier / manual export queue
- LinkedIn manual + API when available

## Brick 7 — Analytics + learning

- SQLite: post → metrics → outcome
- Weekly “what worked / why” report
- Feed winners into few-shot examples

## Brick 8 — Autopilot loop

- Scheduled runs
- Auto-regenerate on gate fail
- Human kill switch
