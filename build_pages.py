"""episodes.py + output/<id>/{audio.mp3,transcript.json}를 이용해
GitHub Pages로 배포할 독립형 플레이어 HTML을 docs/ 폴더에 만든다.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from episodes import EPISODES

BASE = Path(__file__).resolve().parent
TEMPLATE = (BASE / "player_template_standalone.html").read_text(encoding="utf-8")
OUT_DIR = BASE / "output"
DOCS_DIR = BASE / "docs"

DOCS_DIR.mkdir(exist_ok=True)


def build_episode_html(ep: dict, index: int) -> str:
    ep_id = ep["id"]
    audio_bytes = (OUT_DIR / ep_id / "audio.mp3").read_bytes()
    audio_data_uri = f"data:audio/mpeg;base64,{base64.b64encode(audio_bytes).decode('ascii')}"
    transcript_json = (OUT_DIR / ep_id / "transcript.json").read_text(encoding="utf-8")
    transcript = json.loads(transcript_json)
    duration_min = transcript[-1]["end_ms"] / 1000 / 60 if transcript else 0

    prev_ep = EPISODES[index - 1] if index > 0 else None
    next_ep = EPISODES[index + 1] if index < len(EPISODES) - 1 else None
    prev_link = f'<a href="{prev_ep["id"]}.html">← 이전 대화</a>' if prev_ep else "<span></span>"
    next_link = f'<a href="{next_ep["id"]}.html">다음 대화 →</a>' if next_ep else "<span></span>"

    html = TEMPLATE
    html = html.replace("__PAGE_TITLE__", ep["title"])
    html = html.replace("__EYEBROW__", f"Morning Commute · Day {index + 1}")
    html = html.replace("__H1__", ep["title"])
    html = html.replace("__SUBLINE__", f"출근길 10분, 미국인의 진짜 일상 대화를 두 번 들어보세요. {ep['topic']}")
    html = html.replace("__EPISODE_TITLE__", ep["title"])
    html = html.replace("__PREV_LINK__", prev_link)
    html = html.replace("__NEXT_LINK__", next_link)
    html = html.replace("__DURATION_NOTE__", f"{duration_min:.1f}분")
    html = html.replace("__AUDIO_DATA_URI__", audio_data_uri)
    html = html.replace("__TRANSCRIPT_JSON__", transcript_json)
    return html


def build_index_html() -> str:
    rows = "\n".join(
        f'<li><a href="{ep["id"]}.html"><span class="idx">Day {i + 1}</span>'
        f'<span class="ep-title">{ep["title"]}</span>'
        f'<span class="ep-topic">{ep["topic"]}</span></a></li>'
        for i, ep in enumerate(EPISODES)
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>커뮤트 잉글리시 · 전체 목록</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@600;700&family=Noto+Sans+KR:wght@400;500&display=swap" />
<style>
  :root {{ --bg:#f2f4f6; --surface:#fff; --border:#d7dde2; --text:#1b2430; --muted:#5b6773; --accent:#c9631d; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#121820; --surface:#1a2229; --border:#2c3742; --text:#edf1f4; --muted:#93a1ac; --accent:#ff9c4a; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text); font-family:"Sora","Noto Sans KR",system-ui,sans-serif; }}
  .wrap {{ max-width:560px; margin:0 auto; padding:36px 18px 64px; }}
  h1 {{ font-size:24px; margin:0 0 8px; }}
  p.sub {{ color:var(--muted); margin:0 0 24px; font-size:14px; }}
  ul {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:10px; }}
  a {{ display:flex; flex-direction:column; gap:2px; background:var(--surface); border:1px solid var(--border);
       border-radius:14px; padding:14px 16px; text-decoration:none; color:var(--text); }}
  .idx {{ font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--accent); font-weight:700; }}
  .ep-title {{ font-weight:600; font-size:15px; }}
  .ep-topic {{ font-size:13px; color:var(--muted); }}
</style>
</head>
<body>
<div class="wrap">
  <h1>커뮤트 잉글리시</h1>
  <p class="sub">아침 운전 시간에 듣는 미국 일상 대화. 매일 아침 8시에 카톡으로 새 회차 링크가 옵니다.</p>
  <ul>
    {rows}
  </ul>
</div>
</body>
</html>
"""


if __name__ == "__main__":
    for i, ep in enumerate(EPISODES):
        html = build_episode_html(ep, i)
        out_path = DOCS_DIR / f"{ep['id']}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"{out_path} ({len(html) / 1024 / 1024:.2f} MB)")

    (DOCS_DIR / "index.html").write_text(build_index_html(), encoding="utf-8")
    print(f"{DOCS_DIR / 'index.html'} written")
