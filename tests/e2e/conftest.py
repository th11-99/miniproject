"""Playwright E2E 공통 설정.

실행 중인 Streamlit 서버를 대상으로 한다. E2E_BASE_URL이 없으면 수집하지 않는다(일반 pytest에서 제외).

  # 1) 샘플 DB 재생성 후 서버 실행
  .venv/Scripts/python scripts/init_db.py --yes
  .venv/Scripts/python -m streamlit run streamlit_app.py --server.headless true --server.port 8501
  # 2) E2E 실행 (서버와 같은 DB를 E2E_DB_URL로 지정, 기본은 db/maintenance.db)
  E2E_BASE_URL=http://localhost:8501 .venv/Scripts/python -m pytest tests/e2e -p no:cacheprovider

E2E는 서버의 DB에 실제로 등록한다. 검토 전에 DB를 백업하고 끝나면 복원할 것.
"""

import json
import os
from pathlib import Path

import pytest

from scripts.common import DEFAULT_URL, ROOT, fetch_all, is_sqlite, read_connection

BASE_URL = os.environ.get("E2E_BASE_URL")
DB_URL = os.environ.get("E2E_DB_URL", DEFAULT_URL)
SHOTS = ROOT / "reviews" / "screenshots"
CONSOLE_LOG: list[dict] = []

if not BASE_URL:
    collect_ignore_glob = ["test_*.py"]
elif not is_sqlite(DB_URL):
    raise pytest.UsageError("E2E는 로컬 SQLite에서만 실행합니다 (E2E_DB_URL이 운영 DB를 가리킴).")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1280, "height": 900}, "locale": "ko-KR",
            "accept_downloads": True}


@pytest.fixture(autouse=True)
def _collect_console(request, page):
    """브라우저 콘솔 error와 페이지 예외를 모은다 (Streamlit이 내는 알려진 404는 따로 표시)."""
    def on_console(msg):
        if msg.type == "error":
            CONSOLE_LOG.append({"test": request.node.name, "type": "console", "text": msg.text,
                                "url": msg.location.get("url", "")})
    page.on("console", on_console)
    page.on("pageerror", lambda exc: CONSOLE_LOG.append({"test": request.node.name, "type": "pageerror",
                                                          "text": str(exc)}))
    yield


def pytest_sessionfinish(session, exitstatus):
    if BASE_URL:
        SHOTS.mkdir(parents=True, exist_ok=True)
        (SHOTS / "console_errors.json").write_text(json.dumps(CONSOLE_LOG, ensure_ascii=False, indent=2),
                                                   encoding="utf-8")
