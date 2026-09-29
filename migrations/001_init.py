"""001: 최초 스키마 생성.

새 DB는 init_db.py(로컬) 또는 migrate.py(운영, 5단계)가 이 버전부터 순서대로 적용한다.
이후 스키마 변경은 002_*.py 처럼 새 파일로 추가하고 upgrade(conn)에서 ALTER 등으로 변경한다.
기존 파일은 운영 DB에 이미 적용되었을 수 있으므로 절대 수정하지 않는다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import schema  # noqa: E402

# 001 시점의 테이블 목록. schema.py에 테이블이 추가돼도 001은 이 목록만 만든다.
TABLES = [
    "equipment",
    "assemblies",
    "parts",
    "repair_logs",
    "run_logs",
    *(t.name for t in schema.SPEC_TABLES.values()),
    "schema_version",
]


def upgrade(conn) -> None:
    schema.metadata.create_all(conn, tables=[schema.metadata.tables[name] for name in TABLES])
