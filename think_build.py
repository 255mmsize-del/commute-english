"""'영어식 사고' 파트 데이터를 읽어 TTS 오디오를 만들고 docs/think/partN.html 로 발행한다.

항목당 재생 순서:
  (섹션이 바뀌면) 섹션 제목 + 핵심 이미지 설명(한국어)
  표현(영어) → 영어식 사고 풀이(한국어) → 뜻(한국어)
  → 예문 3개: 영어 → 한국어 해석 → 영어 → 영어 (영어 3회)
화면에는 '그림으로 보기'가 풀이 줄의 제목으로 함께 표시된다.

내용이 바뀐 파트만 다시 만든다(docs/think/manifest.json 의 해시 비교) —
매일 CI가 돌아도 시트가 그대로면 오디오를 재생성/재커밋하지 않는다.

사용법: python think_build.py think_all_items.json [part_number ...] [--force]
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

import edge_tts
from pydub import AudioSegment

TTS_MAX_RETRIES = 4
TTS_RETRY_WAIT_SECONDS = 5

BASE = Path(__file__).resolve().parent
TEMPLATE = (BASE / "think_template_standalone.html").read_text(encoding="utf-8")
DOCS_DIR = BASE / "docs" / "think"
AUDIO_DIR = DOCS_DIR / "audio"
MANIFEST_PATH = DOCS_DIR / "manifest.json"
BUILD_VERSION = "2"  # 오디오 구성 방식을 바꾸면 올려서 전체 재빌드 (2: 영어식 사고 설명을 영어 음성으로)

EN_VOICE = "en-US-AvaMultilingualNeural"
KO_EXPLAIN_VOICE = "ko-KR-HyunsuMultilingualNeural"  # 영어 단어가 섞인 해설도 자연스럽게 읽음
KO_VOICE = "ko-KR-SunHiNeural"
RATE = "+0%"
PAUSE_MS = 2000  # 줄 사이 간격
INNER_PAUSE_MS = 1200  # 예문 반복 사이 간격
AUDIO_BITRATE = "48k"  # 음성 전용 모노 - 저장소 용량 절약

HANGUL = re.compile(r"[가-힣]+")
MARK = re.compile(r"\*\*(.+?)\*\*")


def strip_marks(text: str) -> str:
    return MARK.sub(r"\1", text)


def marks_to_html(text: str) -> str:
    """**강조** → 빨간 굵은 글씨 HTML (시트와 같은 강조를 플레이어 화면에도 표시)."""
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return MARK.sub(r'<b class="hl">\1</b>', safe)


EMOJI = re.compile(r"[\U0001F300-\U0001FAFF←-⇿⌀-⏿☀-➿⬀-⯿■-◿✀-➿●]")


def clean_en(text: str) -> str:
    """패턴 표기(주어+동사, ~, 괄호)를 걷어내 영어 TTS가 읽을 문장만 남긴다."""
    t = HANGUL.sub(" ", text)
    t = t.replace("/", ", ").replace("+", " ").replace("~", " ").replace("(", " ").replace(")", " ")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(\s*,\s*)+", ", ", t).strip(" ,")
    return t or text


def clean_ko(text: str) -> str:
    """해설 문장의 기호를 읽기 좋은 쉼표/공백으로 바꾼다."""
    t = EMOJI.sub(" ", text)
    for src, dst in (("→", ", "), ("⇢", ", "), ("=", ", "), ("※", ""), ("~", ""), ("/", ", "),
                     ("'", ""), ('"', ""), ("|", ", "), ("·", ", "), ("①", ", "), ("②", ", "), ("③", ", "), ("④", ", ")):
        t = t.replace(src, dst)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(\s*,\s*)+", ", ", t).strip(" ,")
    return t


async def synth(text: str, voice: str, out_path: Path) -> AudioSegment:
    if out_path.exists() and out_path.stat().st_size > 0:
        return AudioSegment.from_mp3(out_path)
    last_error: Exception | None = None
    for attempt in range(1, TTS_MAX_RETRIES + 1):
        try:
            await edge_tts.Communicate(text, voice, rate=RATE).save(str(out_path))
            return AudioSegment.from_mp3(out_path)
        except Exception as exc:  # noqa: BLE001 - edge-tts는 간헐적으로 NoAudioReceived 등을 던짐
            last_error = exc
            if attempt < TTS_MAX_RETRIES:
                print(f"    [TTS 재시도 {attempt}/{TTS_MAX_RETRIES}] {text[:30]!r}: {exc}")
                await asyncio.sleep(TTS_RETRY_WAIT_SECONDS * attempt)
    raise RuntimeError(f"TTS 합성 {TTS_MAX_RETRIES}회 실패: {text!r}") from last_error


def part_hash(part: dict) -> str:
    raw = BUILD_VERSION + json.dumps(part, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def part_label(part: dict) -> str:
    return f"{part['series']} Part {part['series_part']}"


def part_nav_html(parts: list[dict], current: int) -> str:
    links = []
    for p, part in enumerate(parts, start=1):
        label = f"{part['series'][:2]} {part['series_part']}"
        links.append(f'<span class="current">{label}</span>' if p == current
                     else f'<a href="part{p}.html">{label}</a>')
    return "\n".join(links)


async def build(parts: list[dict], part_num: int) -> None:
    part = parts[part_num - 1]
    items = part["items"]
    lines_dir = BASE / "output" / f"_think_part{part_num}_lines"
    lines_dir.mkdir(parents=True, exist_ok=True)
    for old in lines_dir.glob("*.mp3"):  # 내용이 바뀐 파트라 캐시를 비운다
        old.unlink()

    combined = AudioSegment.empty()
    transcript: list[dict] = []
    cursor_ms = 0

    def add(role: str, item: str, en: str, ko: str, seg: AudioSegment, ex_index: int = 0) -> None:
        nonlocal combined, cursor_ms
        transcript.append({"item": item, "role": role, "ex_index": ex_index, "en": en, "ko": ko,
                           "start_ms": cursor_ms, "end_ms": cursor_ms + len(seg)})
        combined += seg + AudioSegment.silent(duration=PAUSE_MS)
        cursor_ms += len(seg) + PAUSE_MS

    current_section = None
    for i, it in enumerate(items, start=1):
        if it["section_title"] != current_section:
            current_section = it["section_title"]
            intro = f"{clean_ko(current_section)}. 핵심 이미지. {clean_ko(it['section_core'])}"
            seg = await synth(intro, KO_EXPLAIN_VOICE, lines_dir / f"{i:02d}_section.mp3")
            add("section", current_section, "", it["section_core"], seg)

        label = f"{i}. {it['phrase']} (No.{it['no']})"
        add("target", label, it["phrase"], "",
            await synth(clean_en(it["phrase"]), EN_VOICE, lines_dir / f"{i:02d}_target.mp3"))
        thinking_plain = strip_marks(it["thinking"])
        if HANGUL.search(thinking_plain):  # 예전 한국어 풀이
            think_seg = await synth(clean_ko(thinking_plain), KO_EXPLAIN_VOICE, lines_dir / f"{i:02d}_thinking.mp3")
        else:  # Think in English — 원어민 음성으로
            think_seg = await synth(thinking_plain, EN_VOICE, lines_dir / f"{i:02d}_thinking.mp3")
        add("thinking", label, it["picture"], marks_to_html(it["thinking"]), think_seg)
        add("meaning", label, "", it["meaning"],
            await synth(clean_ko(it["meaning"]), KO_VOICE, lines_dir / f"{i:02d}_meaning.mp3"))

        for ex_i, ex in enumerate(it["examples"], start=1):
            en_seg = await synth(ex["en"], EN_VOICE, lines_dir / f"{i:02d}_ex{ex_i}_en.mp3")
            ko_seg = await synth(ex["ko"], KO_VOICE, lines_dir / f"{i:02d}_ex{ex_i}_ko.mp3")
            gap = AudioSegment.silent(duration=INNER_PAUSE_MS)
            add("example", label, ex["en"], ex["ko"], en_seg + gap + ko_seg + gap + en_seg + gap + en_seg, ex_index=ex_i)
        print(f"  [{i}/{len(items)}] {it['phrase']}")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = AUDIO_DIR / f"part{part_num}.mp3"
    combined.set_channels(1).export(audio_path, format="mp3", bitrate=AUDIO_BITRATE)
    duration_min = cursor_ms / 1000 / 60

    title = part_label(part)
    replacements = {
        "__PAGE_TITLE__": title,
        "__EYEBROW__": f"영어식 사고 · {part['series']} · {part['series_part']}/{part['series_total']}",
        "__H1__": title,
        "__SUBLINE__": "표현 → Think in English(원어민 설명, 빨간 글씨가 핵심) → 뜻 → 예문(영어·해석·영어·영어) 순서로 익혀요. 줄을 탭하면 그 지점부터 다시 들을 수 있어요.",
        "__EPISODE_TITLE__": f"{len(items)}개 표현",
        "__ITEM_COUNT__": str(len(items)),
        "__DURATION_NOTE__": f"{duration_min:.1f}분",
        "__AUDIO_SRC__": f"audio/part{part_num}.mp3",
        "__TRANSCRIPT_JSON__": json.dumps(transcript, ensure_ascii=False),
        "__MAIN_END_MS__": str(cursor_ms),
        "__PART_NAV__": part_nav_html(parts, part_num),
    }
    html = TEMPLATE
    for key, value in replacements.items():
        html = html.replace(key, value)
    (DOCS_DIR / f"part{part_num}.html").write_text(html, encoding="utf-8")
    mb = audio_path.stat().st_size / 1024 / 1024
    print(f"Saved: part{part_num}.html ({title}, audio {mb:.1f} MB, {duration_min:.1f}분)")


def build_index(parts: list[dict]) -> None:
    groups: dict[str, list[str]] = {}
    for p, part in enumerate(parts, start=1):
        groups.setdefault(part["series"], []).append(
            f'<li><a href="part{p}.html">Part {part["series_part"]}</a></li>')
    sections = "\n".join(f"<h2>{name}</h2><ul>{''.join(links)}</ul>" for name, links in groups.items())
    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>영어식 사고 - 파트 선택</title>
<style>
  :root {{ color-scheme: light dark; --bg:#f2f4f6; --surface:#fff; --border:#d7dde2; --text:#1b2430; --muted:#5b6773; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg:#121820; --surface:#1a2229; --border:#2c3742; --text:#edf1f4; --muted:#93a1ac; }} }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Noto Sans KR",system-ui,sans-serif; }}
  .wrap {{ max-width:480px; margin:0 auto; padding:36px 16px 64px; }}
  h1 {{ font-size:24px; margin:0 0 8px; }}
  h2 {{ font-size:15px; margin:28px 0 10px; color:var(--muted); }}
  p.sub {{ color:var(--muted); margin:0; font-size:14px; }}
  ul {{ list-style:none; margin:0; padding:0; display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
  a {{ display:flex; align-items:center; justify-content:center; background:var(--surface); border:1px solid var(--border);
       border-radius:14px; padding:18px 0; text-decoration:none; color:var(--text); font-weight:600; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🧠 영어식 사고로 듣기</h1>
  <p class="sub">구동사·숙어와 문장 패턴을 '그림'으로 이해하며 들어요. 파트당 약 20개 표현.</p>
  {sections}
</div>
</body>
</html>
"""
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")



def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    if not args:
        print("사용법: python think_build.py <think_all_items.json> [part_number ...] [--force]", file=sys.stderr)
        sys.exit(1)

    parts = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8")) if MANIFEST_PATH.exists() else {}
    part_nums = [int(p) for p in args[1:]] or list(range(1, len(parts) + 1))

    for part_num in part_nums:
        h = part_hash(parts[part_num - 1])
        html_exists = (DOCS_DIR / f"part{part_num}.html").exists()
        if not force and html_exists and manifest.get(str(part_num)) == h:
            print(f"=== Part {part_num}: 변경 없음, 건너뜀 ===")
            continue
        print(f"=== Part {part_num} ({part_label(parts[part_num - 1])}) ===")
        asyncio.run(build(parts, part_num))
        manifest[str(part_num)] = h
        MANIFEST_PATH.write_text(json.dumps(manifest, indent=1), encoding="utf-8")  # 파트마다 저장 - 중간에 끊겨도 이어서 가능

    # 파트 수가 줄었으면 남는 파일 정리
    for stale in list(manifest):
        if int(stale) > len(parts):
            for f in (DOCS_DIR / f"part{stale}.html", AUDIO_DIR / f"part{stale}.mp3"):
                f.unlink(missing_ok=True)
            del manifest[stale]
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    build_index(parts)
    print("index.html 갱신 완료")


if __name__ == "__main__":
    main()
