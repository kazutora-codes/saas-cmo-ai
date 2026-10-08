# Build log — brick by brick

## Brick 1 — Foundation (done)

- [x] Project layout
- [x] Brand voice YAML
- [x] Free LLM client (Ollama → Groq → Gemini)
- [x] Content agent with intent + originality gates
- [x] CLI: `scripts/generate_content.py`

**You need:** Ollama running locally, **or** a free Groq/Gemini API key in `.env`.

## Brick 2 — Market intel (done)

- [x] `config/intel.yaml` — free sources + scoring keywords
- [x] Collectors: Hacker News API, Lobsters JSON, Reddit public JSON (soft-fail), RSS/Atom
- [x] Relevance ranking vs brand keywords
- [x] Brief → `data/intel/latest.json` (+ timestamped copies)
- [x] Optional LLM refine (themes / opportunities / topics)
- [x] CLI: `scripts/run_market_intel.py`
- [x] Content agent can load intel via `--with-intel`

```bash
python scripts/run_market_intel.py --no-llm
python scripts/run_market_intel.py          # + LLM refine if available
python scripts/generate_content.py --topic "..." --with-intel
```

## Brick 3 — Strategy agent (done)

- [x] `config/strategy.yaml` — cadence, default pillars, formats
- [x] Strategy agent merges brand goals + intel themes/topics
- [x] Weekly pillars + dated calendar (X + LinkedIn)
- [x] Rule-based plan without LLM; optional LLM refine
- [x] CLI: `scripts/run_strategy.py`
- [x] Content CLI: `--from-strategy N` / `--with-strategy`

```bash
python scripts/run_market_intel.py --no-llm
python scripts/run_strategy.py --no-llm
python scripts/generate_content.py --from-strategy 0 --with-intel
```

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
