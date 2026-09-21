"""오늘의 영어 리뷰 페이지 링크를 카카오톡(나에게 보내기)으로 전송한다.

기존에 만들어둔 '카카오-나에게보내기' 로컬 모듈(REST API 키·refresh_token 보유)을
그대로 재사용한다 - 자격증명을 이 저장소에 새로 두지 않기 위함.
"""

from __future__ import annotations

import sys
from pathlib import Path

KAKAO_MODULE_DIR = Path(r"C:\Users\user\Desktop\Study\AI 에이전트 만들기\카카오-나에게보내기")
sys.path.insert(0, str(KAKAO_MODULE_DIR))

import os
os.chdir(KAKAO_MODULE_DIR)  # kakao_client가 상대경로(.env, kakao_token.json, logs/)를 그 폴더 기준으로 찾도록

from kakao_client import KakaoAuthError, KakaoSendError, send_kakao_message  # noqa: E402

PAGE_URL = "https://255mmsize-del.github.io/commute-english/review.html"


def main() -> None:
    summary = sys.argv[1] if len(sys.argv) > 1 else ""
    message = "🗣️ 오늘의 영어 리뷰가 준비됐어요\n\n"
    if summary:
        message += f"{summary}\n\n"
    message += f"{PAGE_URL}"

    try:
        send_kakao_message(message)
        print("전송 완료")
    except (KakaoAuthError, KakaoSendError) as exc:
        print(f"전송 실패: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
