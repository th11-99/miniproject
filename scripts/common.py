"""공통 DB 연결·출력 유틸.

접속 URL 우선순위: 환경변수 DATABASE_URL → st.secrets["database"]["url"] → 로컬 SQLite.
"""

import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, make_url

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "db" / "maintenance.db"
DEFAULT_URL = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

ASSUMED_VALUE_NOTICE = "교체주기·단가·사양 샘플값은 데모용 가정값입니다. 실제 기준은 제조사 매뉴얼·사내 보전기준을 따르세요."


class UserError(Exception):
    """사용자에게 그대로 보여줄 오류 (잘못된 입력, DB 없음 등)."""


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        import streamlit as st

        return st.secrets["database"]["url"]
    except Exception:
        return DEFAULT_URL


def is_sqlite(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def sqlite_path(url: str) -> Path:
    return Path(make_url(url).database)


def _enable_sqlite_fk(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys = ON")


def get_engine(url: str | None = None) -> Engine:
    url = url or get_database_url()
    engine = create_engine(url)
    if is_sqlite(url):
        _enable_sqlite_fk(engine)
    return engine


def get_readonly_engine(url: str | None = None) -> Engine:
    """읽기전용 엔진. SQLite는 mode=ro로 열고, PostgreSQL은 트랜잭션마다 READ ONLY를 건다."""
    url = url or get_database_url()
    if is_sqlite(url):
        path = sqlite_path(url)
        if not path.exists():
            raise UserError(f"DB 파일이 없습니다: {path}. 먼저 python scripts/init_db.py --yes 를 실행하세요.")
        uri = f"{path.resolve().as_uri()}?mode=ro"
        return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))

    engine = create_engine(url)

    @event.listens_for(engine, "begin")
    def _read_only(conn):
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")

    return engine


@contextmanager
def read_connection(url: str | None = None):
    engine = get_readonly_engine(url)
    try:
        with engine.connect() as conn:
            yield conn
    finally:
        engine.dispose()


def fetch_all(conn, sql: str, params: dict | None = None) -> list[dict]:
    return [dict(row._mapping) for row in conn.execute(text(sql), params or {})]


# ---------- CLI 출력 ----------

def json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"직렬화할 수 없는 값: {value!r}")


MAX_CELL_WIDTH = 40


def _width(s: str) -> int:  # 한글 등 전각 문자는 2칸
    return sum(2 if ord(ch) > 0x1100 else 1 for ch in s)


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        s = f"{value:,.2f}".rstrip("0").rstrip(".")
    elif isinstance(value, int) and not isinstance(value, bool):
        s = f"{value:,}"
    elif isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False, default=json_default)
    else:
        s = str(value)
    s = s.replace("\n", " ")
    if _width(s) > MAX_CELL_WIDTH:
        while _width(s) > MAX_CELL_WIDTH - 1:
            s = s[:-1]
        s += "…"
    return s


def _format_table(rows: list[dict]) -> str:
    if not rows:
        return "(결과 없음)"
    headers = list(rows[0].keys())
    cells = [[_cell(r.get(h)) for h in headers] for r in rows]
    numeric = [all(isinstance(r.get(h), (int, float)) and not isinstance(r.get(h), bool) or r.get(h) is None
                   for r in rows) for h in headers]
    widths = [max(_width(h), *(_width(c[i]) for c in cells)) for i, h in enumerate(headers)]

    def line(values, align=True):
        out = []
        for v, w, num in zip(values, widths, numeric):
            pad = " " * (w - _width(v))
            out.append(pad + v if (align and num) else v + pad)
        return " | ".join(out)

    out = [line(headers, align=False), "-+-".join("-" * w for w in widths)]
    out += [line(c) for c in cells]
    return "\n".join(out)


def emit(result, fmt: str = "json") -> None:
    """결과 출력. table 형식은 result["rows"]가 있으면 표로, 없으면 JSON으로 보여준다."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if fmt == "table" and isinstance(result, dict) and isinstance(result.get("rows"), list):
        print(_format_table(result["rows"]))
        count = result.get("row_count", len(result["rows"]))
        note = f" — 앞 {count}행만 표시 (--limit으로 조정)" if result.get("truncated") else ""
        print(f"\n({count}행{note})")
        extra = {k: v for k, v in result.items() if k not in ("rows", "columns", "row_count", "truncated", "limit")}
        if extra:
            print(json.dumps(extra, ensure_ascii=False, default=json_default, indent=2))
        return
    print(json.dumps(result, ensure_ascii=False, default=json_default, indent=2))


def run_cli(func) -> int:
    """UserError를 한국어 메시지 + 종료코드 2로 바꿔 주는 CLI 래퍼."""
    try:
        func()
        return 0
    except UserError as exc:
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        print(f"오류: {exc}", file=sys.stderr)
        return 2
