"""'나의 영어 노트' 앱 데이터: 영어단어장 구글시트 3개 탭 → app_data.json (읽기 전용).

탭: 영어단어장 / 구동사·숙어_영어식사고 / 문장패턴_영어식사고
영어식 사고 D열의 빨간 굵은 강조는 시트 서식(textFormatRuns)에서 읽어 **…** 로 바꾼다.
시트 내용이 그대로면 파일을 다시 쓰지 않는다(매일 빈 커밋 방지).

사용법: python app_fetch.py [출력경로.json]
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from gcreds import LOCAL_SERVICE_ACCOUNT_FILE

SPREADSHEET_ID = "1GPlDWMJ2OhvUR5MjWnWIy6RiwoV1wR8nyi8sVMTDfGQ"
WORD_TAB = "영어단어장"
THINK_TABS = {"phrasal": "구동사·숙어_영어식사고", "pattern": "문장패턴_영어식사고"}
READONLY = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def credentials() -> Credentials:
    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        return Credentials.from_service_account_info(json.loads(env_json), scopes=READONLY)
    return Credentials.from_service_account_file(str(LOCAL_SERVICE_ACCOUNT_FILE), scopes=READONLY)


def is_highlight(fmt: dict) -> bool:
    red = fmt.get("foregroundColorStyle", {}).get("rgbColor", fmt.get("foregroundColor", {}))
    return bool(fmt.get("bold")) and red.get("red", 0) > 0.5 and red.get("green", 0) < 0.4


def marked_text(cell: dict) -> str:
    """서식 구간 중 빨간 굵은 글씨를 **…** 로 감싼다. 인덱스는 UTF-16 단위."""
    text = cell.get("formattedValue", "")
    runs = cell.get("textFormatRuns")
    if not runs:
        return text
    u16 = text.encode("utf-16-le")
    out = [u16[:runs[0].get("startIndex", 0) * 2].decode("utf-16-le")]  # 첫 서식 구간 앞의 기본 서식 글자
    for n, run in enumerate(runs):
        start = run.get("startIndex", 0)
        end = runs[n + 1].get("startIndex", 0) if n + 1 < len(runs) else len(u16) // 2
        seg = u16[start * 2:end * 2].decode("utf-16-le")
        if is_highlight(run.get("format", {})) and seg.strip():
            lead, core, tail = re.match(r"^(\s*)(.*?)(\s*)$", seg, re.S).groups()
            seg = f"{lead}**{core}**{tail}"
        out.append(seg)
    return "".join(out)


def split_examples(cells: list[str]) -> list[list[str]]:
    ex = []
    for c in cells:
        if c.strip():
            en, _, ko = c.partition("\n→ ")
            ex.append([en.strip(), ko.strip()])
    return ex


def words(values: list[list[str]]) -> list[dict]:
    head = values[2]
    col = {name: i for i, name in enumerate(head) if name and name not in head[:i]}  # 같은 이름(비고)은 첫 번째만
    out = []
    for r in values[3:]:
        r = r + [""] * (len(head) - len(r))
        if not r[1].strip():
            continue
        ex = [[r[5].strip(), r[6].strip()]] if r[5].strip() else []
        for k in range(2, 6):
            en_i = col.get(f"예문{k}(영어)")
            if en_i is not None and r[en_i].strip():
                ex.append([r[en_i].strip(), r[en_i + 1].strip()])
        out.append({"no": r[0].strip(), "w": r[1].strip(), "type": r[8].strip(), "mean": r[2].strip(),
                    "syn": r[3].strip(), "ant": r[4].strip(), "note": r[7].strip(), "ex": ex})
    return out


def think(sh: gspread.Spreadsheet, tab: str) -> list[dict]:
    values = sh.worksheet(tab).get_all_values()
    meta = sh.fetch_sheet_metadata(params={
        "includeGridData": "true", "ranges": f"'{tab}'!D1:D{len(values)}",
        "fields": "sheets.data.rowData.values(formattedValue,textFormatRuns)"})
    rich = [(row.get("values") or [{}])[0] for row in meta["sheets"][0]["data"][0].get("rowData", [])]
    sections: list[dict] = []
    for n, r in enumerate(values[3:], start=3):
        r = r + [""] * (8 - len(r))
        if r[0].strip() and not any(c.strip() for c in r[1:]):
            title, _, core = r[0].partition("|")
            sections.append({"title": title.strip(), "core": re.sub(r"^\s*핵심 이미지:\s*", "", core.strip()), "items": []})
            continue
        if not r[1].strip():
            continue
        if not sections:
            sections.append({"title": "", "core": "", "items": []})
        cell = rich[n] if n < len(rich) else {}
        sections[-1]["items"].append({
            "no": r[0].strip(), "expr": r[1].strip(), "pic": r[2].strip(),
            "think": marked_text(cell) if cell.get("formattedValue") else r[3].strip(),
            "ko": r[4].strip(), "ex": split_examples(r[5:8])})
    return [s for s in sections if s["items"]]


def content_hash(data: dict) -> str:
    body = {k: v for k, v in data.items() if k != "synced"}
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main() -> int:
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "app_data.json")
    sh = gspread.authorize(credentials()).open_by_key(SPREADSHEET_ID)
    data = {"words": words(sh.worksheet(WORD_TAB).get_all_values())}
    for key, tab in THINK_TABS.items():
        data[key] = think(sh, tab)
        n = sum(len(s["items"]) for s in data[key])
        hl = sum("**" in i["think"] for s in data[key] for i in s["items"])
        print(f"{tab}: 섹션 {len(data[key])}개 · 항목 {n}개 (강조 {hl})")
    print(f"{WORD_TAB}: {len(data['words'])}개")

    if out_path.exists():
        old = json.loads(out_path.read_text(encoding="utf-8"))
        if content_hash(old) == content_hash(data):
            print("시트 변경 없음 — 그대로 둠")
            return 0
    data = {"synced": datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%m.%d"), **data}
    out_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장: {out_path} ({out_path.stat().st_size // 1024}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
