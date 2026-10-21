"""'나의 영어 노트' 앱 빌드: app_template.html + app_data.json → docs/app/ (GitHub Pages, 홈 화면 설치·오프라인).

만드는 파일: docs/app/index.html, manifest.webmanifest, sw.js (아이콘 png 는 저장소에 고정)
내용이 같으면 파일을 다시 쓰지 않는다.

사용법: python app_build.py [app_data.json]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "app_template.html"
OUT = ROOT / "docs" / "app"

HEAD_EXTRA = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="영어 노트">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" href="icon-192.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
"""

SW_REGISTER = """<script>
if ("serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
</script>
"""

MANIFEST = {
    "name": "나의 영어 노트",
    "short_name": "영어 노트",
    "description": "영어단어장 구글시트로 공부하는 나만의 단어·영어식 사고 학습 앱",
    "lang": "ko",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "background_color": "#F4F5F8",
    "theme_color": "#14213D",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

# 화면(index.html)은 인터넷 먼저 → 실패하면 저장본(오프라인). 아이콘·글꼴은 저장본 먼저.
SW = """const CACHE = "vocab-note-%(ver)s";
const SHELL = ["./", "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("vocab-note-") && k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(res => { const copy = res.clone(); caches.open(CACHE).then(c => c.put("./", copy)); return res; })
      .catch(() => caches.match("./")));
    return;
  }
  e.respondWith(caches.match(req).then(hit => hit || fetch(req).then(res => {
    if (res.ok && (req.url.startsWith(self.location.origin) || req.url.includes("fonts.g"))) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
    return res;
  })));
});
"""


def write_if_changed(path: Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "app_data.json"
    data = data_path.read_text(encoding="utf-8").replace("</", r"<\/")  # <script> 안전
    tpl = TEMPLATE.read_text(encoding="utf-8")
    head, sep, body = tpl.partition("</style>\n")  # 템플릿 앞부분(title·meta·글꼴·style)은 <head> 로
    if not sep:
        raise SystemExit("템플릿에서 </style> 구분을 찾지 못함")
    html = ("<!doctype html>\n<html lang=\"ko\">\n<head>\n" + HEAD_EXTRA + head + sep + SW_REGISTER
            + "</head>\n<body>\n" + body.replace("/*__DATA__*/", data) + "\n</body>\n</html>\n")
    OUT.mkdir(parents=True, exist_ok=True)
    ver = hashlib.sha256(html.encode()).hexdigest()[:10]
    changed = [name for name, text in [
        ("index.html", html),
        ("manifest.webmanifest", json.dumps(MANIFEST, ensure_ascii=False, indent=2) + "\n"),
        ("sw.js", SW % {"ver": ver}),
    ] if write_if_changed(OUT / name, text)]
    print(f"docs/app: {'갱신 ' + ', '.join(changed) if changed else '변경 없음'} ({len(html) // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
