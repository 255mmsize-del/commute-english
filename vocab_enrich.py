"""'영어단어장' 시트의 숙어/문장 행 중 예문2/예문3(J~M열)이 비어있는 새 항목에
Gemini로 예문 2개를 생성해서 채운다(캐시 - 이미 채워진 행은 건너뜀).

로컬 실행: .env(Study/영어단어장/.env)의 GEMINI_API_KEY와 로컬 서비스 계정 파일을 사용.
GitHub Actions 실행: 환경변수 GEMINI_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON을 사용.

사용법: python vocab_enrich.py
"""

from __future__ import annotations

import json
import os
import time

import gspread
import requests

from gcreds import get_credentials

SPREADSHEET_ID = "1GPlDWMJ2OhvUR5MjWnWIy6RiwoV1wR8nyi8sVMTDfGQ"
SHEET_NAME = "영어단어장"
BAD_RANGE = set(range(109, 167))  # 표현/뜻이 밀려있는 손상 구간 - 시트 수정 전까지 건너뜀

EXTRA_HEADERS = ["예문2(영어)", "예문2 해석", "예문3(영어)", "예문3 해석"]
EXTRA_COL_START = 10  # J열

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
MAX_RETRIES = 3
RETRY_WAIT_SECONDS = 8

PROMPT_TEMPLATE = """다음 영어 숙어/표현을 자연스럽게 사용한 서로 다른 예문 문장을 2개 만들어줘.
이미 있는 예문과는 다른 새로운 상황이어야 해. 대화 형식이 아니라 각각 독립된 문장 1개씩.

표현: {phrase}
뜻: {meaning}

아래 JSON 형식으로만 답해라(다른 설명 없이):
{{"ex2_en": "...", "ex2_ko": "...", "ex3_en": "...", "ex3_ko": "..."}}
"""


def call_gemini(phrase: str, meaning: str) -> dict | None:
    api_key = os.environ["GEMINI_API_KEY"]
    prompt = PROMPT_TEMPLATE.format(phrase=phrase, meaning=meaning)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(GEMINI_URL, params={"key": api_key}, json=payload, timeout=30)
            if resp.status_code in (429, 500, 503) and attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SECONDS * attempt)
                continue
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            if all(parsed.get(k) for k in ("ex2_en", "ex2_ko", "ex3_en", "ex3_ko")):
                return parsed
            return None
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SECONDS * attempt)
    print(f"  실패: {phrase} ({last_error})")
    return None


def main() -> None:
    gc = gspread.authorize(get_credentials())
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    values = ws.get_all_values()

    header_row = values[2] if len(values) > 2 else []
    if len(header_row) < EXTRA_COL_START or header_row[EXTRA_COL_START - 1] != EXTRA_HEADERS[0]:
        ws.update(values=[EXTRA_HEADERS], range_name="J3:M3")
        ws.format("J3:M3", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}})

    updates = []
    done = 0
    for i, row in enumerate(values[3:], start=4):
        if not row or not row[1].strip():
            continue
        if len(row) <= 8 or row[8].strip() not in ("숙어", "문장"):
            continue
        try:
            no = int(row[0])
        except ValueError:
            continue
        if no in BAD_RANGE:
            continue

        existing_j = row[9].strip() if len(row) > 9 else ""
        if existing_j:
            continue  # 이미 캐시됨(새 항목만 처리)

        result = call_gemini(row[1], row[2])
        if not result:
            continue

        updates.append({
            "range": f"J{i}:M{i}",
            "values": [[result["ex2_en"], result["ex2_ko"], result["ex3_en"], result["ex3_ko"]]],
        })
        done += 1
        print(f"[{no}] {row[1]} -> 완료 ({done}건째)")

        if len(updates) >= 20:
            ws.batch_update(updates)
            updates = []
        time.sleep(1.2)

    if updates:
        ws.batch_update(updates)

    print(f"\n새로 생성된 항목: {done}건")


if __name__ == "__main__":
    main()
