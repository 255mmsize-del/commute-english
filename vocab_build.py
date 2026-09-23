"""숙어/문장 학습 파트(30개 단위) 데이터를 읽어 TTS 오디오를 만들고
docs/vocab/partN.html 로 발행한다. 각 문장이 끝나면 3초 뒤 다음 문장으로
넘어가도록 균일한 pause를 둔다. 문장(줄)을 탭하면 그 지점부터 다시
재생되므로 안 외워지는 표현만 반복해서 들을 수 있다.
item에 "alt_examples"가 있으면 각 항목 아래 "다른 패턴" 접이식 버튼으로
노출되는 추가 예문을 만든다(기본 재생 흐름에는 포함되지 않음).

사용법: python vocab_build.py vocab_part1_data.json 1
  (두 번째 인자는 파트 번호)
"""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import sys
from pathlib import Path

import edge_tts
from pydub import AudioSegment

BASE = Path(__file__).resolve().parent
TEMPLATE = (BASE / "vocab_template_standalone.html").read_text(encoding="utf-8")
DOCS_DIR = BASE / "docs" / "vocab"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

EN_VOICE = "en-US-AvaMultilingualNeural"
KO_VOICE = "ko-KR-SunHiNeural"
RATE = "+0%"
PAUSE_MS = 3000  # 문장 하나가 끝나면 3초 후 다음 문장
EXAMPLE_REPEATS = 3  # 예문은 3번씩 반복 재생

TOTAL_PARTS = 1  # main()에서 실제 파트 수로 덮어써짐


async def synth(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=RATE)
    await communicate.save(str(out_path))


def part_nav_html(current_part: int, total_parts: int) -> str:
    links = []
    for p in range(1, total_parts + 1):
        if p == current_part:
            links.append(f'<span class="current">Part {p}</span>')
        else:
            links.append(f'<a href="part{p}.html">Part {p}</a>')
    return "\n".join(links)


async def build(items: list[dict], part_num: int) -> None:
    lines_dir = BASE / "output" / f"_vocab_part{part_num}_lines"
    lines_dir.mkdir(parents=True, exist_ok=True)

    combined = AudioSegment.empty()
    transcript = []
    cursor_ms = 0

    def add_segment(role: str, item_label: str, en: str, ko: str, audio_seg: AudioSegment, ex_index: int = 0) -> None:
        nonlocal combined, cursor_ms
        transcript.append({
            "item": item_label,
            "role": role,
            "ex_index": ex_index,
            "en": en,
            "ko": ko,
            "start_ms": cursor_ms,
            "end_ms": cursor_ms + len(audio_seg),
        })
        combined += audio_seg
        cursor_ms += len(audio_seg)
        combined += AudioSegment.silent(duration=PAUSE_MS)
        cursor_ms += PAUSE_MS

    for i, item in enumerate(items, start=1):
        no = item["no"]
        phrase = item["phrase"]
        phrase_tts = item.get("phrase_tts", phrase)
        meaning = item["meaning"]
        item_label = f"{i}. {phrase} (No.{no})"

        target_path = lines_dir / f"{i:02d}_target.mp3"
        meaning_path = lines_dir / f"{i:02d}_meaning.mp3"
        await synth(phrase_tts, EN_VOICE, target_path)
        await synth(meaning, KO_VOICE, meaning_path)

        add_segment("target", item_label, phrase, "", AudioSegment.from_mp3(target_path))
        add_segment("meaning", item_label, "", meaning, AudioSegment.from_mp3(meaning_path))

        for ex_i, ex in enumerate(item["examples"], start=1):
            ex_path = lines_dir / f"{i:02d}_ex{ex_i}.mp3"
            await synth(ex["en"], EN_VOICE, ex_path)
            ex_audio = AudioSegment.from_mp3(ex_path)
            ex_repeated = ex_audio
            for _ in range(EXAMPLE_REPEATS - 1):
                ex_repeated += AudioSegment.silent(duration=PAUSE_MS) + ex_audio
            add_segment("example", item_label, ex["en"], ex["ko"], ex_repeated, ex_index=ex_i)

        print(f"  [{i}/{len(items)}] {phrase}")

    main_duration_min = cursor_ms / 1000 / 60  # "다른 패턴" 풀을 제외한 기본 학습 시간

    # "다른 패턴" 예문 풀: 기본 재생 흐름 밖(파일 끝)에 이어붙이고,
    # 화면에는 각 항목 바로 아래 접이식으로 노출한다(오디오 위치와 화면 순서는 독립적).
    for i, item in enumerate(items, start=1):
        alt_examples = item.get("alt_examples") or []
        if not alt_examples:
            continue
        no = item["no"]
        phrase = item["phrase"]
        item_label = f"{i}. {phrase} (No.{no})"
        for alt_i, ex in enumerate(alt_examples, start=1):
            alt_path = lines_dir / f"{i:02d}_alt{alt_i}.mp3"
            await synth(ex["en"], EN_VOICE, alt_path)
            alt_audio = AudioSegment.from_mp3(alt_path)
            alt_repeated = alt_audio
            for _ in range(EXAMPLE_REPEATS - 1):
                alt_repeated += AudioSegment.silent(duration=PAUSE_MS) + alt_audio
            add_segment("example_alt", item_label, ex["en"], ex["ko"], alt_repeated, ex_index=alt_i)

    # 화면 표시 순서를 항목별로 재배열: 각 항목의 본 예문 뒤에 그 항목의 "다른 패턴"을 붙인다.
    alt_by_item: dict[str, list[dict]] = {}
    main_rows = []
    for row in transcript:
        if row["role"] == "example_alt":
            alt_by_item.setdefault(row["item"], []).append(row)
        else:
            main_rows.append(row)
    transcript[:] = [
        row
        for item_label, group in itertools.groupby(main_rows, key=lambda r: r["item"])
        for row in (*group, *alt_by_item.get(item_label, []))
    ]

    audio_bytes_path = BASE / "output" / f"vocab_part{part_num}_audio.mp3"
    combined.export(audio_bytes_path, format="mp3", bitrate="128k")
    duration_min = main_duration_min

    audio_data_uri = f"data:audio/mpeg;base64,{base64.b64encode(audio_bytes_path.read_bytes()).decode('ascii')}"

    html = TEMPLATE
    html = html.replace("__PAGE_TITLE__", f"숙어 Part {part_num}")
    html = html.replace("__EYEBROW__", f"영어 숙어·문장 공부 · Part {part_num}")
    html = html.replace("__H1__", f"숙어 Part {part_num}")
    html = html.replace("__SUBLINE__", "표현을 듣고 뜻과 예문 3개까지 익혀보세요. 문장이 끝나면 3초 후 다음 문장으로 넘어갑니다. 예문이 익숙해지면 항목마다 '다른 패턴' 버튼으로 새 예문을 들을 수 있어요.")
    html = html.replace("__EPISODE_TITLE__", f"{len(items)}개 표현")
    html = html.replace("__ITEM_COUNT__", str(len(items)))
    html = html.replace("__DURATION_NOTE__", f"{duration_min:.1f}분")
    html = html.replace("__AUDIO_DATA_URI__", audio_data_uri)
    html = html.replace("__TRANSCRIPT_JSON__", json.dumps(transcript, ensure_ascii=False))
    html = html.replace("__PART_NAV__", part_nav_html(part_num, TOTAL_PARTS))

    out_path = DOCS_DIR / f"part{part_num}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Saved: {out_path} ({len(html) / 1024 / 1024:.2f} MB, {duration_min:.1f}min, {len(items)} items)")


def build_index(total_parts: int) -> None:
    rows = "\n".join(
        f'<li><a href="part{p}.html">Part {p}</a></li>' for p in range(1, total_parts + 1)
    )
    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>영어 숙어 공부 - 파트 선택</title>
<style>
  :root {{ color-scheme: light dark; --bg:#f2f4f6; --surface:#fff; --border:#d7dde2; --text:#1b2430; --muted:#5b6773; --accent:#3d6bb3; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#121820; --surface:#1a2229; --border:#2c3742; --text:#edf1f4; --muted:#93a1ac; --accent:#6f9ceb; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Sora","Noto Sans KR",system-ui,sans-serif; }}
  .wrap {{ max-width:480px; margin:0 auto; padding:36px 18px 64px; }}
  h1 {{ font-size:24px; margin:0 0 8px; }}
  p.sub {{ color:var(--muted); margin:0 0 24px; font-size:14px; }}
  ul {{ list-style:none; margin:0; padding:0; display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
  a {{ display:flex; align-items:center; justify-content:center; background:var(--surface); border:1px solid var(--border);
       border-radius:14px; padding:18px 0; text-decoration:none; color:var(--text); font-weight:600; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>영어 숙어·문장 공부</h1>
  <p class="sub">공부할 파트를 선택하세요. 파트당 30개 표현.</p>
  <ul>{rows}</ul>
</div>
</body>
</html>
"""
    out_path = DOCS_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Saved: {out_path}")


def main() -> None:
    global TOTAL_PARTS
    if len(sys.argv) < 2:
        print("사용법: python vocab_build.py <all_parts.json> [part_number ...]", file=sys.stderr)
        print("  part_number를 생략하면 모든 파트를 빌드한다.", file=sys.stderr)
        sys.exit(1)

    data_path = sys.argv[1]
    parts = json.loads(Path(data_path).read_text(encoding="utf-8"))
    TOTAL_PARTS = len(parts)

    if len(sys.argv) > 2:
        part_nums = [int(p) for p in sys.argv[2:]]
    else:
        part_nums = list(range(1, TOTAL_PARTS + 1))

    for part_num in part_nums:
        items = parts[part_num - 1]
        print(f"=== Part {part_num} ({len(items)}개) ===")
        asyncio.run(build(items, part_num))

    build_index(TOTAL_PARTS)


if __name__ == "__main__":
    main()
