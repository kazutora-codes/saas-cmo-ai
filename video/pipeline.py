"""Brick 5: free FFmpeg video pipeline - 9:16 crop, loudnorm, captions, AI-look heuristics."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from core.config import ROOT, load_yaml


def load_video_config() -> dict[str, Any]:
    return load_yaml(ROOT / "config" / "video.yaml")


def _run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def probe(path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    r = _run(cmd, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr.strip() or r.stdout}")
    return json.loads(r.stdout)


def _video_stream(info: dict[str, Any]) -> dict[str, Any]:
    for s in info.get("streams") or []:
        if s.get("codec_type") == "video":
            return s
    raise RuntimeError("No video stream found")


def _has_audio(info: dict[str, Any]) -> bool:
    return any(s.get("codec_type") == "audio" for s in info.get("streams") or [])


def _wrap_caption(text: str, max_chars: int) -> str:
    words = text.split()
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = (" ".join(cur + [w])).strip()
        if len(trial) > max_chars and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines[:4])


def _write_srt(path: Path, text: str, duration: float) -> None:
    end = max(1.0, duration - 0.3)

    def ts(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds - int(seconds)) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    body = text.strip() or " "
    path.write_text(
        f"1\n{ts(0.2)} --> {ts(end)}\n{body}\n",
        encoding="utf-8",
    )


@dataclass
class AILookReport:
    still_ratio: float
    edge_variance: float
    risk_score: float
    regenerate: bool
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ai_look_heuristics(path: Path, cfg: dict[str, Any] | None = None) -> AILookReport:
    """Cheap AI-look proxies using ffmpeg freezedetect + frame variance."""
    cfg = cfg or load_video_config()
    ai = cfg.get("ai_look", {})
    sample = int(ai.get("sample_frames", 24))
    notes: list[str] = []

    freeze = _run(
        [
            "ffmpeg",
            "-i",
            str(path),
            "-vf",
            "freezedetect=n=0.003:d=0.5",
            "-f",
            "null",
            "-",
        ],
        timeout=180,
    )
    freeze_events = len(re.findall(r"freeze_start", freeze.stderr or ""))
    duration = 0.0
    try:
        info = probe(path)
        duration = float(info.get("format", {}).get("duration") or 0)
    except Exception:
        pass
    still_ratio = 0.0
    if duration > 0 and freeze_events:
        still_ratio = min(1.0, (freeze_events * 0.5) / duration)
    if still_ratio > float(ai.get("max_still_ratio", 0.85)):
        notes.append("high_still_ratio")

    with tempfile.TemporaryDirectory() as td:
        pattern = str(Path(td) / "f%03d.png")
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-vf",
                "fps=2,scale=320:-1",
                "-frames:v",
                str(sample),
                pattern,
            ],
            timeout=120,
        )
        frames = sorted(Path(td).glob("f*.png"))
        variances: list[float] = []
        for fr in frames:
            r = _run(
                [
                    "ffmpeg",
                    "-i",
                    str(fr),
                    "-vf",
                    "signalstats,metadata=print:file=-",
                    "-f",
                    "null",
                    "-",
                ],
                timeout=30,
            )
            text = (r.stderr or "") + (r.stdout or "")
            ys = re.findall(r"YAVG=([0-9.]+)", text)
            if ys:
                variances.append(float(ys[0]))
        edge_variance = 0.0
        if len(variances) >= 2:
            mean = sum(variances) / len(variances)
            edge_variance = sum((v - mean) ** 2 for v in variances) / len(variances)
            edge_variance = edge_variance ** 0.5
        if edge_variance < float(ai.get("min_edge_variance", 8.0)):
            notes.append("low_temporal_variance")

    risk = 0.2
    risk += still_ratio * 0.5
    if edge_variance < float(ai.get("min_edge_variance", 8.0)):
        risk += 0.35
    risk = min(1.0, risk)
    regenerate = risk >= float(ai.get("flag_threshold", 0.55))
    if not notes:
        notes.append("ok")

    return AILookReport(
        still_ratio=round(still_ratio, 3),
        edge_variance=round(edge_variance, 3),
        risk_score=round(risk, 3),
        regenerate=regenerate,
        notes=notes,
    )


@dataclass
class ProcessResult:
    input: str
    output: str
    width: int
    height: int
    duration: float
    captions: bool
    loudnorm: bool
    ai_look: dict[str, Any]
    success: bool
    log: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def process_video(
    input_path: Path,
    output_path: Path | None = None,
    caption_text: str = "",
    srt_path: Path | None = None,
    cfg: dict[str, Any] | None = None,
    run_ai_look: bool = True,
) -> ProcessResult:
    """Convert input to vertical 9:16 short with optional captions + loudnorm."""
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg/ffprobe not found on PATH")

    cfg = cfg or load_video_config()
    out_cfg = cfg.get("output", {})
    audio_cfg = cfg.get("audio", {})
    cap_cfg = cfg.get("captions", {})
    paths_cfg = cfg.get("paths", {})

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    out_dir = ROOT / paths_cfg.get("video_out", "data/video/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = out_dir / f"{input_path.stem}_9x16.mp4"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    info = probe(input_path)
    duration = float(info.get("format", {}).get("duration") or 0)
    has_audio = _has_audio(info)

    w = int(out_cfg.get("width", 1080))
    h = int(out_cfg.get("height", 1920))
    fps = int(out_cfg.get("fps", 30))
    crf = int(out_cfg.get("crf", 23))
    preset = str(out_cfg.get("preset", "veryfast"))

    vf_parts = [
        f"scale={w}:{h}:force_original_aspect_ratio=increase",
        f"crop={w}:{h}",
        f"fps={fps}",
    ]

    tmp_srt: Path | None = None
    use_captions = bool(cap_cfg.get("enabled", True)) and (caption_text or srt_path)
    if use_captions:
        if srt_path and Path(srt_path).exists():
            sub = Path(srt_path)
        else:
            tmp_srt = output_path.with_suffix(".tmp.srt")
            wrapped = _wrap_caption(caption_text, int(cap_cfg.get("max_line_chars", 32)))
            _write_srt(tmp_srt, wrapped, duration or 10.0)
            sub = tmp_srt
        sub_esc = str(sub).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        force_style = (
            f"FontSize={int(cap_cfg.get('font_size', 48))},"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BorderStyle=3,"
            f"Outline=1,"
            f"Shadow=0,"
            f"MarginV={int(cap_cfg.get('margin_v', 120))}"
        )
        vf_parts.append(f"subtitles='{sub_esc}':force_style='{force_style}'")

    vf = ",".join(vf_parts)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-c:v",
        str(out_cfg.get("video_codec", "libx264")),
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        str(out_cfg.get("pixel_format", "yuv420p")),
    ]

    if has_audio and audio_cfg.get("loudnorm", True):
        i = audio_cfg.get("i", -16)
        tp = audio_cfg.get("tp", -1.5)
        lra = audio_cfg.get("lra", 11)
        cmd += [
            "-af",
            f"loudnorm=I={i}:TP={tp}:LRA={lra}",
            "-c:a",
            str(out_cfg.get("audio_codec", "aac")),
            "-b:a",
            "128k",
        ]
    elif has_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]

    cmd += ["-movflags", "+faststart", str(output_path)]

    r = _run(cmd, timeout=600)
    if tmp_srt and tmp_srt.exists():
        tmp_srt.unlink(missing_ok=True)

    success = r.returncode == 0 and output_path.exists()
    log = (r.stderr or "")[-2000:]

    ai_report: dict[str, Any] = {}
    if success and run_ai_look:
        try:
            ai_report = ai_look_heuristics(output_path, cfg).to_dict()
        except Exception as e:
            ai_report = {"error": str(e), "regenerate": False}

    out_duration = duration
    if success:
        try:
            out_duration = float(probe(output_path).get("format", {}).get("duration") or duration)
        except Exception:
            pass

    return ProcessResult(
        input=str(input_path),
        output=str(output_path) if success else "",
        width=w,
        height=h,
        duration=round(out_duration, 2),
        captions=bool(use_captions),
        loudnorm=bool(has_audio and audio_cfg.get("loudnorm", True)),
        ai_look=ai_report,
        success=success,
        log=log if not success else "",
    )


def ensure_video_dirs() -> None:
    cfg = load_video_config()
    paths = cfg.get("paths", {})
    for key in ("video_in", "video_out"):
        (ROOT / paths.get(key, f"data/video/{key.split('_')[-1]}")).mkdir(
            parents=True, exist_ok=True
        )
