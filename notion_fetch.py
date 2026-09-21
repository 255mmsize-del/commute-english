"""'영어 복습 노트' Notion 페이지에서 오늘 필요한 범위의 복습 내용을 읽어와
review_build.py가 이해하는 형식(review_input.txt)으로 합쳐서 저장한다.

'내 영어선생님' 프로젝트의 매일 첫 메시지 처리 지침에 따라, Greeting 대화가
새로운 하루가 시작될 때마다 이 Notion 페이지에 다음 구조로 하루치 기록을 남긴다:

    (heading) YYYY-MM-DD (요일)
    (code block)
        1. EN: ...
           KO: ...
           EX: ...
        SUMMARY_KO: ...

이 스크립트는 Notion REST API(공개 API, NOTION_TOKEN 환경변수 필요)로 그 블록들을
읽어서, 요일 규칙에 따라 적절한 날짜(들)의 코드 블록 내용을 review_build.py의
parse_review()로 파싱한 뒤 하나의 review_input.txt로 합친다.

사용법: python notion_fetch.py
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from review_build import parse_review

PAGE_ID = "3e22241a-db3a-8157-a7d1-dcb50e09dd10"
NOTION_VERSION = "2022-06-28"
KST = ZoneInfo("Asia/Seoul")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

WEEKDAY_KR = "월화수목금토일"


def _headers() -> dict[str, str]:
    token = os.environ["NOTION_TOKEN"]
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _rich_text_plain(block: dict, block_type: str) -> str:
    parts = block.get(block_type, {}).get("rich_text", [])
    return "".join(p.get("plain_text", "") for p in parts)


def fetch_day_blocks() -> dict[str, str]:
    """Notion 페이지의 자식 블록을 순회하며 {날짜문자열: 코드블록내용} 딕셔너리를 만든다."""
    day_content: dict[str, str] = {}
    current_date: str | None = None
    url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children"
    params = {"page_size": 100}

    while True:
        resp = requests.get(url, headers=_headers(), params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        for block in data.get("results", []):
            btype = block.get("type", "")
            if btype in ("heading_1", "heading_2", "heading_3"):
                text = _rich_text_plain(block, btype)
                m = DATE_RE.search(text)
                current_date = m.group(0) if m else None
            elif btype == "code" and current_date and current_date not in day_content:
                day_content[current_date] = _rich_text_plain(block, "code")

        if not data.get("has_more"):
            break
        params = {"page_size": 100, "start_cursor": data["next_cursor"]}

    return day_content


def pick_target_dates(day_content: dict[str, str], today: date) -> list[str]:
    weekday = today.weekday()  # 0=월 ... 6=일

    if weekday == 0:  # 월요일: 지난주 월(7일전)~금(3일전)
        candidates = [(today - timedelta(days=n)).isoformat() for n in range(7, 2, -1)]
        return [d for d in candidates if d in day_content]

    if weekday in (5, 6):  # 토(5)/일(6): 이번 주 월요일~금요일
        # 토요일이면 이번주 월=5일전, 금=1일전 / 일요일이면 월=6일전, 금=2일전
        friday_days_back = weekday - 4
        candidates = [(today - timedelta(days=n)).isoformat() for n in range(friday_days_back + 4, friday_days_back - 1, -1)]
        return [d for d in candidates if d in day_content]

    # 화~금: 어제, 없으면 가장 최근 존재하는 날짜로 대체
    yesterday = (today - timedelta(days=1)).isoformat()
    if yesterday in day_content:
        return [yesterday]
    for n in range(2, 15):
        d = (today - timedelta(days=n)).isoformat()
        if d in day_content:
            return [d]
    return []


def build_combined_input(day_content: dict[str, str], dates: list[str]) -> str:
    all_items: list[dict] = []
    summaries: list[str] = []
    for d in dates:
        items, summary = parse_review(day_content[d])
        all_items.extend(items)
        if summary:
            summaries.append(f"{d}: {summary}")

    lines = []
    for i, item in enumerate(all_items, start=1):
        lines.append(f"{i}. EN: {item['en']}")
        lines.append(f"   KO: {item['ko']}")
        lines.append(f"   EX: {item['ex']}")
    combined_summary = " / ".join(summaries) if summaries else "복습할 새 표현이 없습니다."
    lines.append(f"SUMMARY_KO: {combined_summary}")
    return "\n".join(lines)


def main() -> None:
    today = datetime.now(KST).date()
    day_content = fetch_day_blocks()
    dates = pick_target_dates(day_content, today)

    if not dates:
        print("복습할 날짜를 찾지 못했습니다(Notion에 아직 기록이 없을 수 있음).", file=sys.stderr)
        sys.exit(1)

    print(f"오늘({today.isoformat()}, {WEEKDAY_KR[today.weekday()]}요일) 복습 대상 날짜: {dates}")
    combined = build_combined_input(day_content, dates)
    out_path = Path(__file__).resolve().parent / "review_input.txt"
    out_path.write_text(combined, encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
