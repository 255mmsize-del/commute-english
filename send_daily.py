"""매일 아침, 그날의 에피소드 링크를 카카오톡(나에게 보내기)으로 전송한다.

에피소드는 날짜 기준으로 결정적으로 순환한다 (day-of-year % 에피소드 수).
같은 날 여러 번 실행돼도 같은 에피소드가 선택된다.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from episodes import EPISODES

REST_API_KEY = os.environ["KAKAO_REST_API_KEY"]
CLIENT_SECRET = os.environ["KAKAO_CLIENT_SECRET"]
PAGES_BASE_URL = "https://255mmsize-del.github.io/commute-english"
KST = ZoneInfo("Asia/Seoul")


def refresh_access_token() -> str:
    refresh_token = os.environ["KAKAO_REFRESH_TOKEN"]
    data = {
        "grant_type": "refresh_token",
        "client_id": REST_API_KEY,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    result = requests.post("https://kauth.kakao.com/oauth/token", data=data).json()
    if "access_token" not in result:
        raise Exception(f"토큰 갱신 실패: {result}")

    new_refresh_token = result.get("refresh_token")
    if new_refresh_token and new_refresh_token != refresh_token:
        print(f"::add-mask::{new_refresh_token}")
        print("::warning::refresh_token이 갱신되었습니다. Job Summary를 확인하고 GitHub Secret을 업데이트하세요.")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write("### ⚠️ Kakao refresh_token 갱신 필요\n")
                f.write(f"새 refresh_token: `{new_refresh_token}`\n\n")
                f.write("저장소 Settings → Secrets and variables → Actions → KAKAO_REFRESH_TOKEN 에 업데이트하세요.\n")

    return result["access_token"]


def todays_episode() -> dict:
    day_index = datetime.now(KST).timetuple().tm_yday
    return EPISODES[day_index % len(EPISODES)]


def send_message(access_token: str, text: str) -> bool:
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": PAGES_BASE_URL, "mobile_web_url": PAGES_BASE_URL},
    }
    data = {"template_object": json.dumps(template)}
    response = requests.post(url, headers=headers, data=data)
    print(response.status_code, response.text)
    return response.status_code == 200


if __name__ == "__main__":
    episode = todays_episode()
    page_url = f"{PAGES_BASE_URL}/{episode['id']}.html"
    message = (
        "🎧 오늘의 커뮤트 잉글리시\n\n"
        f"{episode['title']}\n"
        f"{episode['topic']}\n\n"
        f"{page_url}"
    )
    token = refresh_access_token()
    send_message(token, message)
