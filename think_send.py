"""오늘의 '영어식 사고' 파트를 정해서(날짜순 순환) 카카오톡으로 링크를 보낸다.
GitHub Actions에서 실행 - 카카오 인증은 vocab_send.py 의 함수를 그대로 재사용한다.

사용법: python think_send.py   (think_all_items.json 이 있어야 함)
필요한 환경변수: KAKAO_REST_API_KEY, KAKAO_CLIENT_SECRET, KAKAO_REFRESH_TOKEN
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from vocab_send import KST, refresh_access_token, send_message

PAGES_BASE_URL = "https://255mmsize-del.github.io/commute-english/think"


def main() -> None:
    parts = json.loads((Path(__file__).resolve().parent / "think_all_items.json").read_text(encoding="utf-8"))
    day_index = datetime.now(KST).timetuple().tm_yday
    part_num = (day_index % len(parts)) + 1
    part = parts[part_num - 1]
    link = f"{PAGES_BASE_URL}/part{part_num}.html"

    message = (f"🧠 오늘의 영어식 사고 - {part['series']} Part {part['series_part']}\n"
               f"표현 {len(part['items'])}개를 그림으로 이해하며 들어요\n\n{link}")
    ok = send_message(refresh_access_token(), message, link)
    if not ok:
        sys.exit(1)
    print(f"전송 완료: Part {part_num} ({part['series']} {part['series_part']})")


if __name__ == "__main__":
    main()
