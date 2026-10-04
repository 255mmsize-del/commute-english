"""'영어단어장' 시트의 숙어/문장 행 중 예문2/예문3(J~M열)이 비어있는 새 항목에
Gemini로 예문 2개를 생성해서 채운다(캐시 - 이미 채워진 행은 건너뜀).
추가로 예문4/예문5(N~Q열, "다른 패턴" 예문 풀)도 같은 방식으로 채운다.

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

ALT_HEADERS = ["예문4(영어)", "예문4 해석", "예문5(영어)", "예문5 해석"]
ALT_COL_START = 14  # N열

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

PROMPT_TEMPLATE_ALT = """다음 영어 숙어/표현에는 이미 아래 3개의 예문이 있어.
사용자가 이 예문들에 너무 익숙해져서, 확실히 다른 문장 구조/상황/어휘로 새로운 예문을 2개 더 공부하고 싶어해.
기존 예문과 겹치지 않는 새로운 패턴으로 만들어줘. 대화 형식이 아니라 각각 독립된 문장 1개씩.

표현: {phrase}
뜻: {meaning}
기존 예문1: {ex1}
기존 예문2: {ex2}
기존 예문3: {ex3}

아래 JSON 형식으로만 답해라(다른 설명 없이):
{{"ex4_en": "...", "ex4_ko": "...", "ex5_en": "...", "ex5_ko": "..."}}
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


def call_gemini_alt(phrase: str, meaning: str, ex1: str, ex2: str, ex3: str) -> dict | None:
    api_key = os.environ["GEMINI_API_KEY"]
    prompt = PROMPT_TEMPLATE_ALT.format(phrase=phrase, meaning=meaning, ex1=ex1, ex2=ex2, ex3=ex3)
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
            if all(parsed.get(k) for k in ("ex4_en", "ex4_ko", "ex5_en", "ex5_ko")):
                return parsed
            return None
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SECONDS * attempt)
    print(f"  실패(alt): {phrase} ({last_error})")
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
    if len(header_row) < ALT_COL_START or header_row[ALT_COL_START - 1] != ALT_HEADERS[0]:
        ws.update(values=[ALT_HEADERS], range_name="N3:Q3")
        ws.format("N3:Q3", {"textFormat": {"bold": True}, "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}})

    updates = []
    done = 0
    done_alt = 0
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

        phrase, meaning = row[1], row[2]
        ex1 = row[5].strip() if len(row) > 5 else ""
        ex2_en = row[9].strip() if len(row) > 9 else ""
        ex3_en = row[11].strip() if len(row) > 11 else ""
        row_range_updates = []

        existing_j = ex2_en
        if not existing_j:
            result = call_gemini(phrase, meaning)
            if result:
                ex2_en, ex3_en = result["ex2_en"], result["ex3_en"]
                row_range_updates.append({
                    "range": f"J{i}:M{i}",
                    "values": [[result["ex2_en"], result["ex2_ko"], result["ex3_en"], result["ex3_ko"]]],
                })
                done += 1
                print(f"[{no}] {phrase} -> 예문2/3 완료 ({done}건째)")
            time.sleep(1.2)

        existing_n = row[13].strip() if len(row) > 13 else ""
        if not existing_n and ex2_en and ex3_en:
            alt_result = call_gemini_alt(phrase, meaning, ex1, ex2_en, ex3_en)
            if alt_result:
                row_range_updates.append({
                    "range": f"N{i}:Q{i}",
                    "values": [[alt_result["ex4_en"], alt_result["ex4_ko"], alt_result["ex5_en"], alt_result["ex5_ko"]]],
                })
                done_alt += 1
                print(f"[{no}] {phrase} -> 예문4/5(다른 패턴) 완료 ({done_alt}건째)")
            time.sleep(1.2)

        updates.extend(row_range_updates)
        if len(updates) >= 20:
            ws.batch_update(updates)
            updates = []

    if updates:
        ws.batch_update(updates)

    print(f"\n새로 생성된 항목: 예문2/3 {done}건, 예문4/5(다른 패턴) {done_alt}건")


if __name__ == "__main__":
    main()
