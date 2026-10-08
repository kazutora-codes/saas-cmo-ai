"""Brick 8/9: autopilot orchestrator - cycle + learning with kill switch."""

from __future__ import annotations

import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import ROOT, load_latest_strategy, load_yaml


def load_autopilot_config() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "autopilot.yaml")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _rule_body(topic: str, platform: str) -> str:
    topic = (topic or "").strip() or "your analytics dashboard"
    if platform == "linkedin":
        return (
            f"{topic}.\n\n"
            "Most teams collect more charts than decisions. "
            "Cut the theater. Ship the answer."
        )
    return (
        f"{topic}.\n\n"
        "Your dashboard has 47 charts. Your team opened 2. Cool product."
    )


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class CycleResult:
    started_at: str
    finished_at: str = ""
    stopped_by_kill: bool = False
    steps: list[StepResult] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "stopped_by_kill": self.stopped_by_kill,
            "steps": [asdict(s) for s in self.steps],
            "error": self.error,
        }


class Autopilot:
    def __init__(self, cfg: dict[str, Any] | None = None) -> None:
        self.cfg = cfg or load_autopilot_config()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for key in ("state_path", "kill_switch", "log_dir"):
            rel = self.cfg.get(key)
            if not rel:
                continue
            p = ROOT / rel
            if key in ("log_dir", "state_path"):
                p.parent.mkdir(parents=True, exist_ok=True)
            if key == "log_dir":
                p.mkdir(parents=True, exist_ok=True)

    def kill_path(self) -> Path:
        return ROOT / self.cfg.get("kill_switch", "data/autopilot/STOP")

    def is_killed(self) -> bool:
        return self.kill_path().exists()

    def arm_kill(self) -> Path:
        p = self.kill_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"stop requested at {_now()}\n", encoding="utf-8")
        return p

    def clear_kill(self) -> bool:
        p = self.kill_path()
        if p.exists():
            p.unlink()
            return True
        return False

    def state_path(self) -> Path:
        return ROOT / self.cfg.get("state_path", "data/autopilot/state.json")

    def save_state(self, payload: dict[str, Any]) -> None:
        path = self.state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_state(self) -> dict[str, Any]:
        path = self.state_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _log_cycle(self, result: CycleResult) -> Path:
        log_dir = ROOT / self.cfg.get("log_dir", "data/autopilot/runs")
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = log_dir / f"cycle_{stamp}.json"
        path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        (log_dir / "latest.json").write_text(
            json.dumps(result.to_dict(), indent=2), encoding="utf-8"
        )
        return path

    def run_cycle(self) -> CycleResult:
        result = CycleResult(started_at=_now())
        cycle_cfg = self.cfg.get("cycle", {})
        try:
            if self.is_killed():
                result.stopped_by_kill = True
                result.steps.append(
                    StepResult("kill_switch", False, "STOP file present - cycle aborted")
                )
                result.finished_at = _now()
                self._log_cycle(result)
                return result

            steps = [
                ("market_intel", self._step_intel),
                ("strategy", self._step_strategy),
                ("content", self._step_content),
                ("publish", self._step_publish),
                ("analytics_import", self._step_analytics),
                ("learning", self._step_learning),
            ]
            for key, fn in steps:
                if not cycle_cfg.get(key, True):
                    continue
                result.steps.append(fn())
                if self.is_killed():
                    result.stopped_by_kill = True
                    result.finished_at = _now()
                    self._log_cycle(result)
                    return result
        except Exception as e:
            result.error = f"{e}\n{traceback.format_exc()[-800:]}"
            result.steps.append(StepResult("fatal", False, str(e)))

        result.finished_at = _now()
        path = self._log_cycle(result)
        state = self.load_state()
        state["last_cycle"] = result.to_dict()
        state["last_log"] = str(path)
        state["updated_at"] = _now()
        self.save_state(state)
        return result

    def _step_intel(self) -> StepResult:
        try:
            from agents.market_intel import MarketIntelAgent

            agent = MarketIntelAgent()
            brief = agent.run(use_llm=False)
            path = agent.save(brief)
            n = 0
            if isinstance(brief, dict):
                n = len(brief.get("top_signals") or brief.get("signals") or [])
            return StepResult("market_intel", True, f"signals≈{n}", {"path": str(path)})
        except Exception as e:
            return StepResult("market_intel", False, str(e))

    def _step_strategy(self) -> StepResult:
        try:
            from agents.strategy_agent import StrategyAgent

            agent = StrategyAgent()
            plan = agent.run(use_llm=False)
            path = agent.save(plan)
            return StepResult(
                "strategy",
                True,
                f"calendar={len(plan.calendar)} pillars={len(plan.pillars)}",
                {"path": str(path), "week_start": plan.week_start},
            )
        except Exception as e:
            return StepResult("strategy", False, str(e))

    def _pick_slots(self) -> list[dict[str, Any]]:
        plan = load_latest_strategy()
        if not plan or not plan.get("calendar"):
            return []
        cal = list(plan["calendar"])
        content_cfg = self.cfg.get("content", {})
        n = int(content_cfg.get("slots_per_cycle", 2))
        today = _today()
        if content_cfg.get("prefer_today", True):
            due = [s for s in cal if str(s.get("date") or "") <= today]
            if due:
                return due[:n]
        return cal[:n]

    def _step_content(self) -> StepResult:
        try:
            from agents.content_agent import ContentAgent
            from agents.quality_gate import rank_variants
            from publish.queue import enqueue

            slots = self._pick_slots()
            if not slots:
                return StepResult("content", False, "no strategy calendar slots")

            content_cfg = self.cfg.get("content", {})
            max_regen = int(content_cfg.get("max_regenerate", 3))
            use_judge = bool(content_cfg.get("use_llm_judge", False))
            agent = ContentAgent()
            queued: list[str] = []
            failed: list[str] = []

            extra = ""
            if content_cfg.get("use_intel", True):
                try:
                    from core.config import load_latest_intel

                    brief = load_latest_intel()
                    if brief:
                        angles = (brief.get("llm_summary") or {}).get(
                            "recommended_topics"
                        ) or brief.get("content_angles") or []
                        if angles:
                            extra = "Market angles: " + "; ".join(str(a) for a in angles[:5])
                except Exception:
                    pass

            for slot in slots:
                if self.is_killed():
                    break
                topic = str(slot.get("topic") or "SaaS growth without fluff")
                platform = str(slot.get("platform") or "x")
                slot_extra = extra
                if slot.get("intent"):
                    slot_extra = f"{slot_extra}\nPost intent: {slot.get('intent')}".strip()

                winner = None
                try:
                    for attempt in range(max_regen):
                        pieces = agent.generate(
                            topic, platform=platform, extra_context=slot_extra
                        )
                        piece_dicts = agent.to_dict_list(pieces)
                        ranked = rank_variants(piece_dicts, use_llm=use_judge)
                        if ranked:
                            winner = ranked[0]
                            break
                        slot_extra = (
                            f"{slot_extra}\nPrevious variants failed quality gates. "
                            "Be more specific, less generic, sharper humor."
                        ).strip()
                except RuntimeError as e:
                    body = _rule_body(topic, platform)
                    ranked = rank_variants(
                        [{"body": body, "platform": platform}], use_llm=False
                    )
                    winner = ranked[0] if ranked else {
                        "body": body,
                        "platform": platform,
                        "notes": f"rule_fallback:{e}",
                    }

                if not winner:
                    failed.append(topic[:40])
                    continue

                item = enqueue(
                    body=str(winner.get("body") or ""),
                    platform=platform,
                    topic=topic,
                    source=f"autopilot:{slot.get('date')}:{slot.get('pillar_id')}",
                    scheduled_for=str(slot.get("date") or ""),
                )
                queued.append(item.id)

            return StepResult(
                "content",
                len(queued) > 0,
                f"queued={len(queued)} failed={len(failed)}",
                {"queue_ids": queued, "failed_topics": failed},
            )
        except Exception as e:
            return StepResult("content", False, str(e))

    def _step_publish(self) -> StepResult:
        try:
            from publish.adapters import export_item, publish_item
            from publish.queue import pending_items, update_item

            items = pending_items()
            if not items:
                return StepResult("publish", True, "nothing pending")

            force = bool(self.cfg.get("publish", {}).get("force_export", True))
            done = 0
            for item in items:
                if self.is_killed():
                    break
                result = export_item(item) if force else publish_item(item)
                status = (
                    "published"
                    if result.ok and result.mode == "api"
                    else ("exported" if result.ok else "failed")
                )
                update_item(
                    item.id,
                    status=status,
                    result={
                        "mode": result.mode,
                        "message": result.message,
                        "external_id": result.external_id,
                        "export_path": result.export_path,
                    },
                    notes=result.message,
                )
                done += 1
            return StepResult("publish", True, f"processed={done}")
        except Exception as e:
            return StepResult("publish", False, str(e))

    def _step_analytics(self) -> StepResult:
        try:
            from analytics.store import import_from_queue, init_db

            init_db()
            n = import_from_queue()
            return StepResult("analytics_import", True, f"imported={n}")
        except Exception as e:
            return StepResult("analytics_import", False, str(e))

    def _step_learning(self) -> StepResult:
        try:
            from analytics.learn import load_learning_config, run_learning_cycle

            cfg = load_learning_config()
            if not cfg.get("enabled_in_autopilot", True):
                return StepResult("learning", True, "skipped (disabled)")
            data = run_learning_cycle(use_llm=False)
            return StepResult(
                "learning",
                True,
                f"rules_do={len(data.get('rules_do') or [])} rules_dont={len(data.get('rules_dont') or [])}",
                {"path": data.get("_path", "")},
            )
        except Exception as e:
            return StepResult("learning", False, str(e))

    def run_loop(
        self, interval_minutes: int | None = None, max_cycles: int | None = None
    ) -> None:
        loop_cfg = self.cfg.get("loop", {})
        interval = (
            interval_minutes
            if interval_minutes is not None
            else int(loop_cfg.get("interval_minutes", 60))
        )
        max_c = max_cycles if max_cycles is not None else int(loop_cfg.get("max_cycles", 0))
        cycles = 0
        while True:
            if self.is_killed():
                print("Kill switch active - exiting loop.")
                break
            cycles += 1
            print(f"\n=== Autopilot cycle {cycles} @ {_now()} ===")
            result = self.run_cycle()
            for s in result.steps:
                mark = "OK" if s.ok else "FAIL"
                print(f"  [{mark}] {s.name}: {s.detail}")
            if result.stopped_by_kill:
                print("Stopped by kill switch.")
                break
            if result.error:
                print(f"  error: {result.error[:200]}")
            if max_c and cycles >= max_c:
                print(f"Reached max_cycles={max_c}")
                break
            print(f"Sleeping {interval} minutes… (create {self.kill_path()} to stop)")
            remaining = interval * 60
            while remaining > 0:
                if self.is_killed():
                    print("Kill switch during sleep - exiting.")
                    return
                chunk = min(15, remaining)
                time.sleep(chunk)
                remaining -= chunk
