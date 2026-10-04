"""episodes.py의 모든 에피소드에 대해 음성(mp3)과 자막(json)을 생성한다."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import edge_tts
from pydub import AudioSegment

from episodes import EPISODES

OUT_DIR = Path(__file__).resolve().parent / "output"
PAUSE_BETWEEN_LINES_MS = 300
RATE = "+8%"


async def synthesize_line(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=RATE)
    await communicate.save(str(out_path))


async def build_episode(ep: dict) -> None:
    ep_id = ep["id"]
    lines_dir = OUT_DIR / ep_id / "_lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    line_paths = []
    for i, (speaker, voice, en, ko) in enumerate(ep["dialogue"]):
        out_path = lines_dir / f"{i:03d}_{speaker}.mp3"
        if not out_path.exists():
            await synthesize_line(en, voice, out_path)
        line_paths.append(out_path)
    print(f"[{ep_id}] {len(line_paths)} lines synthesized")

    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=PAUSE_BETWEEN_LINES_MS)
    transcript = []
    cursor_ms = 0
    for i, p in enumerate(line_paths):
        seg = AudioSegment.from_mp3(p)
        speaker, voice, en, ko = ep["dialogue"][i]
        transcript.append(
            {
                "index": i,
                "speaker": speaker,
                "en": en,
                "ko": ko,
                "start_ms": cursor_ms,
                "end_ms": cursor_ms + len(seg),
            }
        )
        combined += seg
        cursor_ms += len(seg)
        if i < len(line_paths) - 1:
            combined += pause
            cursor_ms += PAUSE_BETWEEN_LINES_MS

    audio_path = OUT_DIR / ep_id / "audio.mp3"
    transcript_path = OUT_DIR / ep_id / "transcript.json"
    combined.export(audio_path, format="mp3", bitrate="128k")
    transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")

    duration_sec = len(combined) / 1000
    print(f"[{ep_id}] done: {duration_sec:.1f}s ({duration_sec / 60:.1f}min) -> {audio_path}")


async def main() -> None:
    for ep in EPISODES:
        await build_episode(ep)


if __name__ == "__main__":
    asyncio.run(main())
