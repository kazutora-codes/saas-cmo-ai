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

## Brick 4 — Stronger quality gates (done)

- [x] `config/quality.yaml` — thresholds + ranking weights
- [x] Heuristic gates: intent, originality, humor, brand fit
- [x] LLM-as-judge for humor/brand calibration (optional)
- [x] Variant ranking + winner selection before publish
- [x] CLI: `scripts/rank_content.py`
- [x] Wired into `generate_content.py` (`--no-rank` / `--no-llm-judge`)

```bash
python scripts/generate_content.py --from-strategy 0 --with-intel --no-llm-judge
python scripts/rank_content.py data/content/SOME.json --no-llm
```

## Brick 5 — Video pipeline (done)

- [x] `config/video.yaml` — 9:16 output, loudnorm, caption style, AI-look thresholds
- [x] FFmpeg: center crop → 1080×1920, loudnorm, burned-in captions (SRT or text)
- [x] AI-look heuristics (freeze ratio + temporal variance) → `regenerate` flag
- [x] CLI: `scripts/process_video.py`
- [x] Prefers hybrid real footage; pure AI video often flagged

```bash
python scripts/process_video.py path/to/clip.mp4 -c "Your team opened 2 of 47 charts."
python scripts/process_video.py path/to/clip.mp4 --srt captions.srt -o data/video/out/short.mp4
```

## Brick 6 — Publish adapters (done)

- [x] `config/publish.yaml` — platforms, char limits, export options
- [x] Local JSON queue (`data/publish/queue.json`)
- [x] Manual export package (`.txt` / `.md` / `.json`) — always works offline
- [x] X adapter: API when free-tier keys present, else export
- [x] LinkedIn adapter: export by default (API optional if token set)
- [x] CLI: `scripts/queue_post.py`, `scripts/publish.py`

```bash
python scripts/queue_post.py --body "Your dashboard has 47 charts." --platform x
python scripts/queue_post.py --from-content data/content/SOME.json
python scripts/publish.py                  # export or API
python scripts/publish.py --force-export   # always write files
python scripts/queue_post.py --list
```

## Brick 7 — Analytics + learning (done)

- [x] `config/analytics.yaml` — thresholds + few-shot settings
- [x] SQLite: posts / metrics / outcomes (`data/analytics/metrics.db`)
- [x] Import published queue items + manual metric logging
- [x] Winner / loser labeling from engagement
- [x] Weekly report + pattern notes
- [x] Few-shot winners fed into content agent
- [x] CLI: `scripts/log_metrics.py`, `scripts/analytics_report.py`

```bash
python scripts/log_metrics.py --init --import-queue
python scripts/log_metrics.py --post-id 1 --impressions 1200 --likes 48 --replies 6 --reposts 9
python scripts/log_metrics.py --evaluate --list
python scripts/analytics_report.py --days 7
```

## Brick 8 — Autopilot loop

- Scheduled runs
- Auto-regenerate on gate fail
- Human kill switch
