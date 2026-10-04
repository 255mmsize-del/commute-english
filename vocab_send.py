"""오늘 공부할 숙어 파트를 정해서(요일순 순환) 카카오톡으로 링크를 보낸다.
GitHub Actions에서 실행 - 환경변수만으로 동작한다(로컬 토큰 파일 불필요).

사용법: python vocab_send.py <total_parts>
필요한 환경변수: KAKAO_REST_API_KEY, KAKAO_CLIENT_SECRET, KAKAO_REFRESH_TOKEN
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

REST_API_KEY = os.environ["KAKAO_REST_API_KEY"]
CLIENT_SECRET = os.environ["KAKAO_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["KAKAO_REFRESH_TOKEN"]
PAGES_BASE_URL = "https://255mmsize-del.github.io/commute-english/vocab"
KST = ZoneInfo("Asia/Seoul")


def refresh_access_token() -> str:
    data = {
        "grant_type": "refresh_token",
        "client_id": REST_API_KEY,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    }
    result = requests.post("https://kauth.kakao.com/oauth/token", data=data, timeout=10).json()
    if "access_token" not in result:
        raise RuntimeError(f"토큰 갱신 실패: {result}")
    new_refresh_token = result.get("refresh_token")
    if new_refresh_token and new_refresh_token != REFRESH_TOKEN:
        print("::warning::refresh_token이 갱신되었습니다. GitHub Secret KAKAO_REFRESH_TOKEN을 업데이트하세요.")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("### ⚠️ Kakao refresh_token 갱신 필요\n")
                f.write(f"새 refresh_token: `{new_refresh_token}`\n\n")
    return result["access_token"]


def send_message(access_token: str, text: str, link: str) -> bool:
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": link, "mobile_web_url": link},
    }
    data = {"template_object": json.dumps(template, ensure_ascii=False)}
    response = requests.post(url, headers=headers, data=data, timeout=10)
    print(response.status_code, response.text)
    return response.status_code == 200


def main() -> None:
    total_parts = int(sys.argv[1])
    day_index = datetime.now(KST).timetuple().tm_yday
    part_num = (day_index % total_parts) + 1
    link = f"{PAGES_BASE_URL}/part{part_num}.html"

    message = f"📚 오늘의 영어 숙어 - Part {part_num}\n\n{link}"
    token = refresh_access_token()
    ok = send_message(token, message, link)
    if not ok:
        sys.exit(1)
    print(f"전송 완료: Part {part_num}")


if __name__ == "__main__":
    main()
