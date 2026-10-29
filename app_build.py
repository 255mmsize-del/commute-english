"""'나의 영어 노트' 앱 빌드: app_template.html + app_data.json → docs/app/ (GitHub Pages, 홈 화면 설치·오프라인).

만드는 파일: docs/app/index.html, manifest.webmanifest, sw.js (아이콘 png 는 저장소에 고정)
내용이 같으면 파일을 다시 쓰지 않는다.

app_fixes.json(app_examples_gen.py 가 만듦)을 덧입힌다: 시트에서 단어와 뜻·예문이 어긋난 행의 보정,
표현이 들어간 예문 3개(ex3) 보강. 시트 자체는 건드리지 않는다.

사용법: python app_build.py [app_data.json]
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from app_example_match import example_lines, qa_pairs  # noqa: E402
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
    "background_color": "#F5F0E6",
    "theme_color": "#F5F0E6",
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


def apply_fixes(data: dict) -> dict:
    """손상 행 보정 + 표현이 들어간 질문/답변 대화 3개(ex3)와 그 안의 문장(ex3s, 말하기·배열 문제용).
    보정은 시트 뜻 첫 줄(sig)이 그대로일 때만 — 시트를 고치면 시트 값이 우선."""
    path = ROOT / "app_fixes.json"
    fixes = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    fix, qa = fixes.get("fix", {}), fixes.get("qa", {})
    cpath = ROOT / "app_corrections.json"
    corr = json.loads(cpath.read_text(encoding="utf-8")).get("words", {}) if cpath.exists() else {}
    fixed, applied = 0, set()

    def add_qa(it: dict, en: str, key: str) -> None:
        it["ex3"] = (qa_pairs(en, it["ex"])[:1] + qa.get(key, []))[:3]
        it["ex3s"] = [s for s, _ in example_lines(en, it["ex3"] + it["ex"])[:4]]

    for w in data["words"]:
        k = f'{w["no"]}|{w["w"]}'   # 보정·예문 키는 시트 원래 단어 기준
        f = fix.get(k)
        if f and w["mean"].split("\n")[0].strip() == f["sig"]:
            w.update({x: f[x] for x in ("mean", "syn", "ant", "note", "ex")}); fixed += 1
        if k in corr:
            w.update({x: v for x, v in corr[k].items() if x in ("w", "mean", "ex")}); applied.add(k)
        w["w"] = cap_i(w["w"])
        add_qa(w, w["w"], f"w|{k}")
    for key, src in (("phrasal", "p"), ("pattern", "t")):
        for sec in data[key]:
            for it in sec["items"]:
                qk = f'{src}|{it["no"]}|{it["expr"]}'
                it["expr"] = cap_i(it["expr"])
                add_qa(it, it["expr"], qk)
    stale = [k for k in corr if k not in applied]
    items = data["words"] + [i for key in ("phrasal", "pattern") for s in data[key] for i in s["items"]]
    print(f"보정 {fixed}개 · 오타 보정 {len(applied)}개 · 질문/답변 3개 미만 {sum(len(i['ex3']) < 3 for i in items)}개 / {len(items)}개")
    if stale:
        print(f"app_corrections.json: 시트에서 이미 고쳐져 지워도 되는 항목 {len(stale)}개 → {', '.join(stale)}")
    warn_typos(data)
    return data


def cap_i(s: str) -> str:
    """문장 맨 앞 소문자 i(i wish to, i'm …)를 I 로."""
    return re.sub(r"^i(?=[ '’])", "I", s)


def warn_typos(data: dict) -> None:
    """오타 의심: 표현 속 영어 낱말이 앱 전체 예문 어디에도 안 나오면 알린다(빌드는 계속)."""
    toks = lambda t: re.findall(r"[a-z]+(?:'[a-z]+)?", t.lower())  # noqa: E731
    items = [(w["no"], w["w"], w["ex"] + w.get("ex3", [])) for w in data["words"]]
    items += [(it["no"], it["expr"], it["ex"] + it.get("ex3", [])) for k in ("phrasal", "pattern") for s in data[k] for it in s["items"]]
    vocab = {t for _, _, ex in items for e, _ in ex for t in toks(e)}
    skip = {"sb", "sth", "someone", "something", "one's", "ing", "adj"}
    known = lambda t: t in vocab or t in skip or len(t) <= 2 or any(v.startswith(t) for v in vocab)  # noqa: E731  altered·sprained 도 인정
    sus = [f"No.{no} {en}" for no, en, _ in items
           if not all(known(t) for t in toks(re.sub(r"\(.*?\)|[가-힣]+|[~…+/]", " ", en)))]
    if sus:
        print(f"오타 의심 {len(sus)}개(예문에 한 번도 안 나오는 낱말): {' · '.join(sus)}")


def main() -> int:
    data_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "app_data.json"
    data = json.dumps(apply_fixes(json.loads(data_path.read_text(encoding="utf-8"))), ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", r"<\/")  # <script> 안전
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
