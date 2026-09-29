"""테스트용 DB 픽스처.

- 기본: 임시 SQLite 샘플 DB (실제 db/maintenance.db는 건드리지 않는다)
- TEST_DATABASE_URL에 PostgreSQL을 지정하면 같은 테스트를 PostgreSQL에서도 한 번 더 실행한다.
  테이블을 지우고 다시 만들기 때문에 DB 이름에 'test'가 들어간 전용 DB만 허용한다.
  (DATABASE_URL은 운영 DB일 수 있어 테스트에 쓰지 않는다)
"""

import os
import shutil
from datetime import date

import pytest
from sqlalchemy.engine import make_url

from scripts import schema
from scripts.common import get_engine, is_sqlite, sqlite_path
from scripts.init_db import build_database, seed_sample_data
from scripts.migrate_lib import apply_pending

END_DATE = date(2026, 9, 28)
TEST_PG_URL = os.environ.get("TEST_DATABASE_URL")
BACKENDS = ["sqlite"] + (["postgresql"] if TEST_PG_URL else [])


def rebuild_postgres(url: str) -> None:
    if "test" not in (make_url(url).database or ""):
        raise RuntimeError("TEST_DATABASE_URL의 DB 이름에 'test'가 없어 초기화를 거부합니다.")
    engine = get_engine(url)
    try:
        schema.metadata.drop_all(engine)
        with engine.begin() as conn:
            apply_pending(conn)
            seed_sample_data(conn, seed=42, end_date=END_DATE)
    finally:
        engine.dispose()


@pytest.fixture(scope="session", params=BACKENDS)
def db_url(request, tmp_path_factory):
    """세션 공용 샘플 DB. 읽기 테스트용이므로 여기에 쓰지 않는다."""
    if request.param == "postgresql":
        rebuild_postgres(TEST_PG_URL)
        return TEST_PG_URL
    path = tmp_path_factory.mktemp("db") / "test.db"
    url = f"sqlite:///{path.as_posix()}"
    build_database(url, seed=42, end_date=END_DATE)
    return url


@pytest.fixture
def writable_db_url(db_url, tmp_path):
    """쓰기 테스트용 DB. SQLite는 공용 DB 파일 복사본, PostgreSQL은 테스트 후 다시 초기화한다."""
    if is_sqlite(db_url):
        copy = tmp_path / "writable.db"
        shutil.copy(sqlite_path(db_url), copy)
        yield f"sqlite:///{copy.as_posix()}"
    else:
        yield db_url
        rebuild_postgres(db_url)
