"""구글시트의 '영어식 사고' 해설 탭(구동사·숙어 / 문장패턴)을 읽어
파트(20개 단위)로 나눈 뒤 think_all_items.json으로 저장한다.

시트가 유일한 데이터 소스다. 탭 내용은 워크스페이스 스킬
vocab-phrasal-thinking / vocab-pattern-thinking 의 build_sheet.py 가 만든다.
섹션 머리줄 형식("<제목>   |   핵심 이미지: <원리>")을 그 스크립트와 맞춰야 한다.

사용법: python think_fetch.py
"""

from __future__ import annotations

import json
from pathlib import Path

import gspread

from gcreds import get_credentials

SPREADSHEET_ID = "1GPlDWMJ2OhvUR5MjWnWIy6RiwoV1wR8nyi8sVMTDfGQ"
SERIES = [
    # (탭 이름, 화면/카톡에 쓸 시리즈 이름)
    ("구동사·숙어_영어식사고", "구동사·숙어"),
    ("문장패턴_영어식사고", "문장패턴"),
]
SECTION_SEP = "   |   핵심 이미지: "
PART_SIZE = 20
HEADER_ROWS = 3  # 제목 / 안내 / 열 머리글
THINK_COL = 3  # D열: 영어식 사고 (빨간 굵은 글씨 강조 포함)


def runs_to_markup(text: str, runs: list[dict]) -> str:
    """Sheets textFormatRuns 중 굵은 글씨 구간을 **…** 로 감싼 문자열로 바꾼다."""
    if not runs:
        return text
    out, bounds = [], [(r.get("startIndex", 0), bool(r.get("format", {}).get("bold"))) for r in runs]
    bounds.append((len(text), False))
    if bounds[0][0] > 0:
        out.append(text[:bounds[0][0]])
    for (start, bold), (end, _) in zip(bounds, bounds[1:]):
        seg = text[start:end]
        out.append(f"**{seg}**" if bold and seg.strip() else seg)
    return "".join(out)


def fetch_think_markup(sh: gspread.Spreadsheet, tab_name: str) -> dict[int, str]:
    """D열 각 칸을 강조 마크업이 포함된 문자열로 읽어 {0-based 행: 문자열} 로 돌려준다."""
    meta = sh.fetch_sheet_metadata({"ranges": [f"'{tab_name}'!D:D"], "includeGridData": True,
                                    "fields": "sheets.data.rowData.values(formattedValue,textFormatRuns)"})
    result: dict[int, str] = {}
    for i, row in enumerate(meta["sheets"][0]["data"][0].get("rowData", [])):
        values = row.get("values") or [{}]
        cell = values[0]
        if cell.get("formattedValue"):
            result[i] = runs_to_markup(cell["formattedValue"], cell.get("textFormatRuns", []))
    return result


def parse_tab(values: list[list[str]], think_markup: dict[int, str] | None = None) -> list[dict]:
    items: list[dict] = []
    section_title, section_core = "", ""
    for row_idx, row in enumerate(values):
        if row_idx < HEADER_ROWS:
            continue
        row = row + [""] * (8 - len(row))
        if row[0].strip() and not row[1].strip():
            title, _, core = row[0].partition(SECTION_SEP)
            section_title, section_core = title.strip(), core.strip()
            continue
        if not row[1].strip():
            continue
        examples = []
        for cell in row[5:8]:
            en, _, ko = cell.partition("\n→ ")
            if en.strip():
                examples.append({"en": en.strip(), "ko": ko.strip()})
        if len(examples) != 3:
            print(f"  [건너뜀] 예문 3개가 아님: {row[1]}")
            continue
        items.append({
            "section_title": section_title,
            "section_core": section_core,
            "no": row[0].strip(),
            "phrase": row[1].strip(),
            "picture": row[2].strip(),
            "thinking": (think_markup or {}).get(row_idx, row[3]).strip(),
            "meaning": row[4].strip(),
            "examples": examples,
        })
    return items


def main() -> None:
    sh = gspread.authorize(get_credentials()).open_by_key(SPREADSHEET_ID)
    parts: list[dict] = []
    for tab_name, series_label in SERIES:
        items = parse_tab(sh.worksheet(tab_name).get_all_values(), fetch_think_markup(sh, tab_name))
        # 파트 수는 PART_SIZE 기준으로 정하되, 마지막 파트가 너무 작지 않게 고르게 나눈다
        n_parts = max(1, -(-len(items) // PART_SIZE))
        bounds = [round(k * len(items) / n_parts) for k in range(n_parts + 1)]
        chunks = [items[bounds[k]:bounds[k + 1]] for k in range(n_parts)]
        for k, chunk in enumerate(chunks, start=1):
            parts.append({"series": series_label, "series_part": k, "series_total": len(chunks), "items": chunk})
        print(f"{series_label}: {len(items)}개 -> {len(chunks)}개 파트")

    out_path = Path(__file__).resolve().parent / "think_all_items.json"
    out_path.write_text(json.dumps(parts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"총 {len(parts)}개 파트 저장: {out_path}")


if __name__ == "__main__":
    main()
