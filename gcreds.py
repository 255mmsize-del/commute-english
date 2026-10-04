"""구글 서비스 계정 인증정보를 로컬 파일(개발용) 또는 환경변수
GOOGLE_SERVICE_ACCOUNT_JSON(GitHub Actions용)에서 가져온다.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LOCAL_SERVICE_ACCOUNT_FILE = Path(r"C:\Users\user\Desktop\Study\.secrets\google-service-account.json")


def get_credentials() -> Credentials:
    env_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if env_json:
        info = json.loads(env_json)
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    return Credentials.from_service_account_file(str(LOCAL_SERVICE_ACCOUNT_FILE), scopes=SCOPES)
