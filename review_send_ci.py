"""GitHub Actions에서 실행되는 카카오톡 전송 스크립트.
로컬 kakao_client.py(파일 기반 토큰)와 달리, GitHub Secrets의 환경변수만으로
동작한다 - send_daily.py와 동일한 인증 방식을 재사용한다.

사용법: python review_send_ci.py "SUMMARY_KO 텍스트"
필요한 환경변수: KAKAO_REST_API_KEY, KAKAO_CLIENT_SECRET, KAKAO_REFRESH_TOKEN
"""

from __future__ import annotations

import json
import os
import sys

import requests

REST_API_KEY = os.environ["KAKAO_REST_API_KEY"]
CLIENT_SECRET = os.environ["KAKAO_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["KAKAO_REFRESH_TOKEN"]
PAGE_URL = "https://255mmsize-del.github.io/commute-english/review.html"


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
                f.write("저장소 Settings → Secrets and variables → Actions → KAKAO_REFRESH_TOKEN 에 업데이트하세요.\n")

    return result["access_token"]


def send_message(access_token: str, text: str) -> bool:
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {access_token}"}
    template = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": PAGE_URL, "mobile_web_url": PAGE_URL},
    }
    data = {"template_object": json.dumps(template, ensure_ascii=False)}
    response = requests.post(url, headers=headers, data=data, timeout=10)
    print(response.status_code, response.text)
    return response.status_code == 200


def main() -> None:
    summary = sys.argv[1] if len(sys.argv) > 1 else ""
    message = "🗣️ 오늘의 영어 리뷰가 준비됐어요\n\n"
    if summary:
        message += f"{summary}\n\n"
    message += PAGE_URL

    token = refresh_access_token()
    ok = send_message(token, message)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
