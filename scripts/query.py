"""읽기전용 조회. SELECT/WITH 단일 문장만 허용한다.

  python scripts/query.py --schema
  python scripts/query.py "SELECT part_id, part_name, aliases FROM parts WHERE aliases LIKE '%죠%'"
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from scripts.common import UserError, emit, read_connection, run_cli  # noqa: E402

FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "REPLACE", "UPSERT", "MERGE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "ATTACH", "DETACH", "PRAGMA", "VACUUM", "REINDEX", "ANALYZE", "GRANT", "REVOKE", "COPY", "CALL", "DO",
    "SET", "RESET", "LOCK", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE", "EXECUTE", "PREPARE",
}


def _strip_literals(sql: str) -> str:
    """문자열·식별자 리터럴과 주석을 지운 SQL (키워드 검사용).

    문자열과 주석을 왼쪽부터 한 번에 읽어 나간다. 따로따로 지우면 주석 안의 따옴표가
    뒤쪽 따옴표와 짝을 지어 `;`와 DELETE를 문자열로 숨길 수 있다.
    닫히지 않은 문자열·주석이 있으면 UserError.
    """
    out, i, n = [], 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch in ("'", '"'):
            j = i + 1
            while True:
                j = sql.find(ch, j)
                if j == -1:
                    raise UserError("닫히지 않은 문자열이 있습니다.")
                if j + 1 < n and sql[j + 1] == ch:  # '' 또는 "" 이스케이프
                    j += 2
                    continue
                break
            out.append(ch * 2)
            i = j + 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            out.append(" ")
            i = n if j == -1 else j
        elif sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            if j == -1:
                raise UserError("닫히지 않은 주석이 있습니다.")
            out.append(" ")
            i = j + 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def validate_sql(sql: str) -> str:
    """허용되는 조회문이면 끝의 세미콜론을 뗀 SQL을 돌려주고, 아니면 UserError."""
    cleaned = sql.strip()
    if not cleaned:
        raise UserError("SQL이 비어 있습니다.")
    bare = _strip_literals(cleaned).strip()
    bare = bare[:-1] if bare.endswith(";") else bare  # 끝의 세미콜론 하나만 허용
    if ";" in bare:
        raise UserError("여러 문장은 실행할 수 없습니다. SELECT 한 문장만 입력하세요.")
    cleaned = cleaned.rstrip().removesuffix(";").rstrip() if cleaned.rstrip().endswith(";") else cleaned
    words = re.findall(r"[A-Za-z_]+", bare)
    if not words or words[0].upper() not in ("SELECT", "WITH"):
        raise UserError("조회(SELECT/WITH)만 허용됩니다. 등록은 log_repair.py를 사용하세요.")
    found = {w.upper() for w in words}
    # REPLACE는 문자열 함수 replace(...)로만 쓰일 때 허용
    if "REPLACE" in found and len(re.findall(r"\breplace\b", bare, re.I)) == len(re.findall(r"\breplace\s*\(", bare, re.I)):
        found.discard("REPLACE")
    bad = sorted(found & FORBIDDEN)
    if bad:
        raise UserError(f"조회 전용입니다. 허용되지 않는 키워드: {', '.join(bad)}")
    return cleaned


DEFAULT_LIMIT = 200


def run_query(sql: str, url: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """조회 결과를 최대 limit행까지 돌려준다. 더 있으면 truncated=True."""
    if limit < 1:
        raise UserError("--limit은 1 이상이어야 합니다.")
    cleaned = validate_sql(sql)
    with read_connection(url) as conn:
        try:
            result = conn.execute(text(cleaned))
            columns = list(result.keys())
            fetched = result.fetchmany(limit + 1)
        except Exception as exc:  # DB 오류를 사용자 메시지로
            raise UserError(f"SQL 실행 오류: {getattr(exc, 'orig', exc)}") from exc
    rows = [dict(zip(columns, r)) for r in fetched[:limit]]
    return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": len(fetched) > limit,
            "limit": limit}


def get_schema(url: str | None = None) -> dict:
    with read_connection(url) as conn:
        insp = inspect(conn)
        tables = {}
        for name in sorted(insp.get_table_names()):
            fks = {fk["constrained_columns"][0]: f'{fk["referred_table"]}.{fk["referred_columns"][0]}'
                   for fk in insp.get_foreign_keys(name)}
            pk = set(insp.get_pk_constraint(name)["constrained_columns"])
            tables[name] = [
                {"column": c["name"], "type": str(c["type"]), "pk": c["name"] in pk,
                 "nullable": c["nullable"], "fk": fks.get(c["name"])}
                for c in insp.get_columns(name)
            ]
    return {"tables": tables}


def main() -> None:
    parser = argparse.ArgumentParser(description="읽기전용 조회 (SELECT/WITH 단일 문장)")
    parser.add_argument("sql", nargs="?", help="실행할 SELECT문")
    parser.add_argument("--schema", action="store_true", help="테이블·컬럼 구조 출력")
    parser.add_argument("--format", choices=("json", "table"), default="json")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"최대 출력 행 수 (기본 {DEFAULT_LIMIT})")
    args = parser.parse_args()

    if args.schema:
        result = get_schema()
        if args.format == "table":
            rows = [{"table": t, **c} for t, cols in result["tables"].items() for c in cols]
            emit({"rows": rows}, "table")
        else:
            emit(result)
        return
    if not args.sql:
        parser.error("SQL 또는 --schema 가 필요합니다.")
    emit(run_query(args.sql, limit=args.limit), args.format)


if __name__ == "__main__":
    sys.exit(run_cli(main))
