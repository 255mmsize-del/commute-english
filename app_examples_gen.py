"""영어 노트 앱용 예문 보강·손상 행 보정 데이터(app_fixes.json)를 만든다. 구글시트는 건드리지 않는다.

1) 손상 행(단어 칸과 뜻·예문 칸이 어긋난 행): 시트의 단어(B열)를 기준으로 뜻·동의어·반의어·비고·예문을
   Gemini로 새로 만들어 fix 에 둔다. 앱은 시트 뜻 첫 줄(sig)이 그대로일 때만 덮어쓴다
   → 사용자가 시트를 직접 고치면 자동으로 시트 값을 쓴다.
2) 모든 표현(단어장·구동사·문장패턴)이 '그 표현이 들어간 질문/답변 대화' 3개를 갖도록
   시트 대화에서 뽑은 쌍(최대 1개)에 모자란 만큼 새로 만들어 qa 에 둔다.

한 번 만든 항목은 다시 만들지 않는다(캐시). 새 표현이 생기면 이 스크립트를 다시 돌리면 된다.
사용법: PYTHONUTF8=1 python app_examples_gen.py
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv

from app_example_match import matcher, qa_pairs

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "app_data.json"
FIXES = ROOT / "app_fixes.json"
load_dotenv(ROOT.parent / "영어단어장" / ".env")

MODEL = "gemini-3.1-flash-lite"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
BATCH = 12
WORKERS = 4

# 시트에서 단어 칸과 내용 칸이 어긋난 행(2026-10-21 점검). 단어(B열)가 정답, 나머지를 새로 만든다.
BROKEN = {str(n) for n in range(109, 167)} | {"1010"}

FIX_PROMPT = """너는 한국인 영어 학습자용 단어장을 만든다. 아래 영어 표현 각각에 대해 JSON 배열로만 답해라(설명 없이).
각 원소: {{"w": 표현 그대로, "mean": "1. 뜻\\n2. 뜻" (번호 매긴 한국어 뜻 1~4개), "syn": "1. 영어(한국어)\\n2. ..." (동의어 1~3개),
"ant": "반의어(한국어)" (없으면 빈 문자열), "note": "한국어 1~2문장 사용 팁",
"dialog_en": "A: ...\\nB: ...\\nA: ..." (표현이 그대로 들어간 자연스러운 3줄 대화), "dialog_ko": "A: ...\\nB: ...\\nA: ...",
"ex": [["독립된 영어 예문 1문장", "한국어 해석"], ["...", "..."]] (표현이 들어간 서로 다른 상황 2개)}}

표현 목록:
{items}"""

QA_PROMPT = """한국인 영어 학습자용 질문/답변 예문을 만든다. 아래 각 표현마다 요청한 개수만큼
A가 묻고(물음표로 끝나는 질문 1문장) B가 답하는(1~2문장) 짧고 자연스러운 일상 대화를 만들어라.
표현(또는 시제·인칭만 바꾼 형태)이 질문이나 답변에 반드시 들어가야 하고, 가능하면 답변에 넣어라.
쌍마다 상황이 달라야 하고 기존 예문과도 달라야 한다. 패턴(+ 주어 + 동사 등)은 실제 문장으로 채워 써라.
JSON 배열로만 답해라(설명 없이): [{{"id": 번호, "qa": [{{"q": "영어 질문", "a": "영어 답변", "qk": "질문 해석", "ak": "답변 해석"}}, ...]}}]

{items}"""


def gemini(prompt: str) -> list:
    key = os.environ["GEMINI_API_KEY"]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"}}
    for attempt in range(5):
        try:
            r = requests.post(URL, params={"key": key}, json=body, timeout=120)
            if r.status_code == 200:
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            print(f"  Gemini {r.status_code}, 재시도 {attempt + 1}", flush=True)
        except (requests.RequestException, KeyError, json.JSONDecodeError) as e:
            print(f"  Gemini 오류 {type(e).__name__}, 재시도 {attempt + 1}", flush=True)
        time.sleep(8 * (attempt + 1))
    print("  Gemini 호출 포기 — 다음 실행 때 다시 시도", flush=True)
    return []


def all_items(data: dict, fixes: dict):
    """(qa 키, 표현, 뜻 한 줄, 예문 목록) — 단어장은 손상 행 보정본 기준."""
    for w in data["words"]:
        k = f'{w["no"]}|{w["w"]}'
        f = fixes["fix"].get(k)
        ok = f and w["mean"].split("\n")[0].strip() == f["sig"]
        yield f"w|{k}", w["w"], (f["mean"] if ok else w["mean"]).split("\n")[0], f["ex"] if ok else w["ex"]
    for key, src in (("phrasal", "p"), ("pattern", "t")):
        for sec in data[key]:
            for it in sec["items"]:
                yield f'{src}|{it["no"]}|{it["expr"]}', it["expr"], it["ko"].split("\n")[0], it["ex"]


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    fixes = json.loads(FIXES.read_text(encoding="utf-8")) if FIXES.exists() else {}
    fixes.setdefault("fix", {}); fixes.setdefault("qa", {}); fixes.pop("extra", None)
    lock = threading.Lock()

    def save() -> None:
        FIXES.write_text(json.dumps(fixes, ensure_ascii=False, indent=1), encoding="utf-8")

    # 1) 손상 행 다시 만들기
    todo = [w for w in data["words"] if w["no"] in BROKEN and f'{w["no"]}|{w["w"]}' not in fixes["fix"]]
    for i in range(0, len(todo), 15):
        part = todo[i:i + 15]
        print(f"손상 행 보정 {i + 1}~{i + len(part)} / {len(todo)}", flush=True)
        by_w = {r.get("w", "").strip().lower(): r for r in gemini(FIX_PROMPT.format(items="\n".join(f"- {w['w']}" for w in part)))}
        for w in part:
            r = by_w.get(w["w"].strip().lower())
            if not r:
                print("  응답 없음:", w["w"], flush=True); continue
            ex = [[r["dialog_en"].strip(), r["dialog_ko"].strip()]] + [[e.strip(), k.strip()] for e, k in r.get("ex", [])][:2]
            fixes["fix"][f'{w["no"]}|{w["w"]}'] = {"sig": w["mean"].split("\n")[0].strip(), "mean": r["mean"].strip(),
                                                   "syn": r.get("syn", "").strip(), "ant": r.get("ant", "").strip(),
                                                   "note": r.get("note", "").strip(), "ex": ex}
        save()

    # 2) 질문/답변 대화 3개 채우기
    need = []
    for k, en, mean, ex in all_items(data, fixes):
        have = len(qa_pairs(en, ex)[:1]) + len(fixes["qa"].get(k, []))
        if have < 3:
            need.append((k, en, mean, 3 - have, ex))
    print(f"질문/답변 보강 대상 {len(need)}개 (대화 {sum(n[3] for n in need)}쌍)", flush=True)
    batches = [need[i:i + BATCH] for i in range(0, len(need), BATCH)]
    done = [0]

    def run(part) -> None:
        lines = [f'{n}. 표현: {en} / 뜻: {mean} / 개수: {cnt} / 기존 예문: {" | ".join(e.replace(chr(10), " ") for e, _ in ex)[:160]}'
                 for n, (k, en, mean, cnt, ex) in enumerate(part)]
        res = gemini(QA_PROMPT.format(items="\n".join(lines)))
        with lock:
            for r in res if isinstance(res, list) else []:
                try:
                    k, en, mean, cnt, _ = part[int(r["id"])]
                except (KeyError, ValueError, IndexError, TypeError):
                    continue
                m = matcher(en)
                got = []
                for x in r.get("qa", []):
                    q, a = str(x.get("q", "")).strip(), str(x.get("a", "")).strip()
                    # 질문으로 끝나는 쌍이 원칙. "You should ~" 처럼 제안·응답형 표현은 A가 물음표가 아닐 수 있어 함께 받는다
                    if q and a:
                        got.append(([f"A: {q}\nB: {a}", f'A: {str(x.get("qk", "")).strip()}\nB: {str(x.get("ak", "")).strip()}'], m is None or m(q + " " + a)))
                good = [g for g, ok in got if ok] or [g for g, _ in got]   # 표현이 안 잡히면(축약·오타 표현) 그래도 받음
                fixes["qa"][k] = fixes["qa"].get(k, []) + good[:cnt]
            done[0] += 1
            if done[0] % 5 == 0 or done[0] == len(batches):
                save(); print(f"  {done[0]}/{len(batches)} 묶음 완료", flush=True)

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(run, batches))
    save()
    short = sum(1 for k, en, _, ex in all_items(data, fixes) if len(qa_pairs(en, ex)[:1]) + len(fixes["qa"].get(k, [])) < 3)
    print(f"완료: 보정 {len(fixes['fix'])}개 · 질문/답변 보유 {len(fixes['qa'])}개 · 3개 미만 {short}개", flush=True)


if __name__ == "__main__":
    main()
