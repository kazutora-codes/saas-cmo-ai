# Build log — brick by brick

## Brick 1 — Foundation (done)

- [x] Project layout, brand voice, free LLM client, content agent

## Brick 2 — Market intel (done)

- [x] HN, Lobsters, Reddit, RSS collectors + brief

## Brick 3 — Strategy agent (done)

- [x] Weekly pillars + dated calendar

## Brick 4 — Stronger quality gates (done)

- [x] Heuristic + LLM judge, variant ranking

## Brick 5 — Video pipeline (done)

- [x] FFmpeg crop, loudnorm, captions, AI-look heuristics

## Brick 6 — Publish adapters (done)

- [x] Queue, export, X/LinkedIn adapters

## Brick 7 — Analytics + learning (done)

- [x] SQLite posts/metrics/outcomes, weekly report, few-shot

## Brick 8 — Autopilot loop (done)

- [x] Full cycle, regenerate-on-fail, kill switch, `--loop`

```bash
python scripts/run_autopilot.py --once
python scripts/run_autopilot.py --loop --interval 60 --max-cycles 3
python scripts/run_autopilot.py --stop
python scripts/run_autopilot.py --resume
python scripts/run_autopilot.py --status
```

## Brick 9 — Daily learning & self-improvement (done)

- [x] `config/learning.yaml` — thresholds, store path, autopilot flag
- [x] Extract durable rules from winner/loser outcomes
- [x] Topic boost / avoid lists for strategy
- [x] Winning hooks + banned fluff phrases
- [x] Inject learnings into content agent prompts
- [x] Inject topic boosts into strategy agent
- [x] Autopilot step: `learning` after analytics import
- [x] CLI: `scripts/run_learning.py`

```bash
python scripts/run_learning.py --import-queue
python scripts/run_learning.py --show
python scripts/run_autopilot.py --once   # includes learning step
```
