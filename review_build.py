"""'내 영어선생님' 프로젝트의 예약된 작업이 생성한 복습 텍스트(review_input.txt)를
읽어서 TTS 오디오를 만들고, docs/review.html 로 재발행한다.

review_input.txt 형식(예약된 작업 지침과 일치해야 함):
    1. EN: I've been meaning to call you.
       KO: 한동안 전화하려고 했어요.
       EX: I've been meaning to try that new cafe.
    2. EN: ...
       KO: ...
       EX: ...
    SUMMARY_KO: 오늘은 ...

사용법: python review_build.py review_input.txt
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import edge_tts
from pydub import AudioSegment

BASE = Path(__file__).resolve().parent
TEMPLATE = (BASE / "review_template_standalone.html").read_text(encoding="utf-8")
DOCS_DIR = BASE / "docs"
DOCS_DIR.mkdir(exist_ok=True)

KST = ZoneInfo("Asia/Seoul")
EN_VOICE = "en-US-AvaMultilingualNeural"
KO_VOICE = "ko-KR-SunHiNeural"
RATE = "+0%"

PAUSE_AFTER_TARGET_MS = 2200  # 따라 말할 시간
PAUSE_SHORT_MS = 400
PAUSE_BETWEEN_ITEMS_MS = 900

TARGET_DURATION_MS = 5 * 60 * 1000  # 학습량이 적은 날에도 이만큼은 채운다(반복 재생으로)
MAX_PASSES = 12

ITEM_RE = re.compile(
    r"EN:\s*(?P<en>.+?)\s*\n\s*KO:\s*(?P<ko>.+?)\s*\n\s*EX:\s*(?P<ex>.+?)\s*(?=\n\s*\d+\.\s*EN:|\n\s*SUMMARY_KO:|\Z)",
    re.DOTALL,
)
SUMMARY_RE = re.compile(r"SUMMARY_KO:\s*(.+)", re.DOTALL)


def parse_review(text: str) -> tuple[list[dict], str]:
    items = [
        {"en": m.group("en").strip(), "ko": m.group("ko").strip(), "ex": m.group("ex").strip()}
        for m in ITEM_RE.finditer(text)
    ]
    if not items:
        raise ValueError("복습 항목을 파싱하지 못했습니다. review_input.txt 형식을 확인하세요.")
    summary_m = SUMMARY_RE.search(text)
    summary = summary_m.group(1).strip() if summary_m else ""
    return items, summary


async def synth(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=RATE)
    await communicate.save(str(out_path))


async def build(items: list[dict], summary: str) -> None:
    lines_dir = BASE / "output" / "_review_lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    combined = AudioSegment.empty()
    transcript = []
    cursor_ms = 0

    def add_segment(role: str, item_num: int, en: str, ko: str, audio_seg: AudioSegment, pause_after_ms: int) -> None:
        nonlocal combined, cursor_ms
        transcript.append({
            "item": item_num,
            "role": role,
            "en": en,
            "ko": ko,
            "start_ms": cursor_ms,
            "end_ms": cursor_ms + len(audio_seg),
        })
        combined += audio_seg
        cursor_ms += len(audio_seg)
        if pause_after_ms:
            combined += AudioSegment.silent(duration=pause_after_ms)
            cursor_ms += pause_after_ms

    # 문장별 오디오는 한 번만 합성해서 캐시하고, 5분을 채울 때까지 전체 목록을
    # 여러 바퀴(패스) 반복 재생한다 - 그날 배운 표현이 적어도 복습 분량은 확보한다.
    clips = []
    for i, item in enumerate(items, start=1):
        target_path = lines_dir / f"{i:02d}_target.mp3"
        meaning_path = lines_dir / f"{i:02d}_meaning.mp3"
        example_path = lines_dir / f"{i:02d}_example.mp3"

        await synth(item["en"], EN_VOICE, target_path)
        await synth(item["ko"], KO_VOICE, meaning_path)
        await synth(item["ex"], EN_VOICE, example_path)

        clips.append({
            "item": item,
            "target": AudioSegment.from_mp3(target_path),
            "meaning": AudioSegment.from_mp3(meaning_path),
            "example": AudioSegment.from_mp3(example_path),
        })

    pass_num = 1
    while True:
        label_suffix = "" if pass_num == 1 else f" · {pass_num}회차 반복"
        for i, clip in enumerate(clips, start=1):
            item = clip["item"]
            label = f"{i}{label_suffix}"
            add_segment("target", label, item["en"], "", clip["target"], PAUSE_AFTER_TARGET_MS)
            add_segment("meaning", label, "", item["ko"], clip["meaning"], PAUSE_SHORT_MS)
            add_segment("example", label, item["ex"], "", clip["example"], PAUSE_BETWEEN_ITEMS_MS)
        if cursor_ms >= TARGET_DURATION_MS or pass_num >= MAX_PASSES:
            break
        pass_num += 1

    audio_bytes_path = BASE / "output" / "review_audio.mp3"
    combined.export(audio_bytes_path, format="mp3", bitrate="128k")
    duration_min = len(combined) / 1000 / 60

    audio_data_uri = f"data:audio/mpeg;base64,{base64.b64encode(audio_bytes_path.read_bytes()).decode('ascii')}"
    today = datetime.now(KST).strftime("%Y-%m-%d")
    weekday_kr = "월화수목금토일"[datetime.now(KST).weekday()]

    html = TEMPLATE
    html = html.replace("__PAGE_TITLE__", f"{today} 영어 리뷰")
    html = html.replace("__EYEBROW__", f"내 영어선생님 · {today} ({weekday_kr})")
    html = html.replace("__H1__", "오늘의 영어 리뷰")
    html = html.replace("__SUBLINE__", "운전하면서 듣고 따라 말해보세요. 표현을 들은 뒤 잠깐 멈추면 따라 말할 시간입니다.")
    html = html.replace("__EPISODE_TITLE__", f"{len(items)}개 표현 복습")
    html = html.replace("__DURATION_NOTE__", f"{duration_min:.1f}분")
    html = html.replace("__AUDIO_DATA_URI__", audio_data_uri)
    html = html.replace("__TRANSCRIPT_JSON__", json.dumps(transcript, ensure_ascii=False))
    summary_html = f"<b>오늘의 요약</b> · {summary}" if summary else ""
    html = html.replace("__SUMMARY_HTML__", summary_html)

    out_path = DOCS_DIR / "review.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Saved: {out_path} ({len(html) / 1024 / 1024:.2f} MB, {duration_min:.1f}min, {len(items)} items)")


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: python review_build.py <review_input.txt>", file=sys.stderr)
        sys.exit(1)
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    items, summary = parse_review(text)
    asyncio.run(build(items, summary))


if __name__ == "__main__":
    main()
