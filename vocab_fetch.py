"""구글시트 '영어단어장'에서 숙어/문장 항목(단어 제외)을 전부 읽어와
30개씩 파트로 나눈 뒤 vocab_all_items.json으로 저장한다.

시트가 유일한 데이터 소스다 - 예문2/예문3(J~M열)은 enrich_extra_examples.py가
Gemini로 미리 채워둔 캐시를 그대로 읽기만 한다(여기서는 생성하지 않음).

No.109~166 구간은 표현/뜻이 밀려있는 데이터 손상이 있어 시트가 고쳐질 때까지
계속 제외한다.

사용법: python vocab_fetch.py
"""

from __future__ import annotations

import json
from pathlib import Path

import gspread

from gcreds import get_credentials

SPREADSHEET_ID = "1GPlDWMJ2OhvUR5MjWnWIy6RiwoV1wR8nyi8sVMTDfGQ"
SHEET_NAME = "영어단어장"

BAD_RANGE = set(range(109, 167))  # 표현/뜻이 밀려있는 손상 구간 - 시트 수정 전까지 제외
PART_SIZE = 30


def main() -> None:
    gc = gspread.authorize(get_credentials())
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    values = ws.get_all_values()

    items = []
    skipped_bad = 0
    skipped_no_examples = 0
    for row in values[3:]:
        if not row or not row[1].strip():
            continue
        if len(row) <= 8 or row[8].strip() not in ("숙어", "문장"):
            continue
        try:
            no = int(row[0])
        except ValueError:
            continue
        if no in BAD_RANGE:
            skipped_bad += 1
            continue

        ex1_en, ex1_ko = row[5].strip(), row[6].strip()
        ex2_en = row[9].strip() if len(row) > 9 else ""
        ex2_ko = row[10].strip() if len(row) > 10 else ""
        ex3_en = row[11].strip() if len(row) > 11 else ""
        ex3_ko = row[12].strip() if len(row) > 12 else ""
        ex4_en = row[13].strip() if len(row) > 13 else ""
        ex4_ko = row[14].strip() if len(row) > 14 else ""
        ex5_en = row[15].strip() if len(row) > 15 else ""
        ex5_ko = row[16].strip() if len(row) > 16 else ""

        if not (ex1_en and ex2_en and ex3_en):
            skipped_no_examples += 1
            continue

        alt_examples = (
            [{"en": ex4_en, "ko": ex4_ko}, {"en": ex5_en, "ko": ex5_ko}]
            if ex4_en and ex5_en else []
        )

        # 대화 형식(A:/B:)이면 표현이 들어간 한 줄만 뽑아 단문 예문으로 쓴다
        def pick_line(en_block: str, ko_block: str) -> tuple[str, str]:
            en_lines = [l.split(":", 1)[-1].strip() for l in en_block.split("\n") if ":" in l]
            ko_lines = [l.split(":", 1)[-1].strip() for l in ko_block.split("\n") if ":" in l]
            phrase_words = [w for w in row[1].split() if len(w) >= 3]
            for i, l in enumerate(en_lines):
                if any(w.lower() in l.lower() for w in phrase_words) or not phrase_words:
                    return l, ko_lines[i] if i < len(ko_lines) else (ko_lines[0] if ko_lines else "")
            return (en_lines[0] if en_lines else en_block), (ko_lines[0] if ko_lines else ko_block)

        ex1_en_s, ex1_ko_s = pick_line(ex1_en, ex1_ko) if "\n" in ex1_en or ":" in ex1_en else (ex1_en, ex1_ko)

        items.append({
            "no": no,
            "phrase": row[1],
            "meaning": row[2].split("\n")[0].lstrip("1. ").strip() or row[2],
            "examples": [
                {"en": ex1_en_s, "ko": ex1_ko_s},
                {"en": ex2_en, "ko": ex2_ko},
                {"en": ex3_en, "ko": ex3_ko},
            ],
            "alt_examples": alt_examples,
        })

    parts = [items[i:i + PART_SIZE] for i in range(0, len(items), PART_SIZE)]

    out_path = Path(__file__).resolve().parent / "vocab_all_items.json"
    out_path.write_text(json.dumps(parts, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"총 {len(items)}개 항목 -> {len(parts)}개 파트로 분할 저장: {out_path}")
    print(f"(제외: 손상 구간 {skipped_bad}건, 예문 미완성 {skipped_no_examples}건)")


if __name__ == "__main__":
    main()
