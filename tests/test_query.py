import pytest
from sqlalchemy import text

from scripts.common import UserError, read_connection
from scripts.query import get_schema, run_query, validate_sql


@pytest.mark.parametrize("sql", [
    "INSERT INTO equipment VALUES ('CNC-99', 'x', NULL)",
    "UPDATE parts SET stock_qty = 0",
    "DELETE FROM repair_logs",
    "DROP TABLE parts",
    "SELECT 1; DROP TABLE parts",
    "SELECT 1; SELECT 2",
    "WITH x AS (SELECT 1) INSERT INTO equipment VALUES ('a', 'b', NULL)",
    "PRAGMA table_info(parts)",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT 1 /* 닫히지 않은 주석",
    "SELECT 'unterminated",
    "",
    # 4단계 검토 C-1: 주석 안 따옴표로 세미콜론·쓰기 문장을 숨기는 우회
    "SELECT 1 /* ' */ ; DELETE FROM parts; /* ' */",
    "SELECT 1 -- '\n; COMMIT; DELETE FROM repair_logs --'",
])
def test_rejects_non_select(sql):
    with pytest.raises(UserError):
        validate_sql(sql)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM parts",
    "select part_id from parts;",
    "WITH t AS (SELECT 1 AS a) SELECT a FROM t",
    "SELECT ';DROP TABLE parts' AS s",  # 문자열 안의 키워드는 허용
    "SELECT replace(part_name, ' ', '') FROM parts",
    "SELECT part_id FROM parts -- 주석",
])
def test_accepts_select(sql):
    validate_sql(sql)


def test_run_query_returns_rows(db_url):
    result = run_query("SELECT part_id, part_name FROM parts WHERE aliases LIKE '%라이브센터%'", db_url)
    assert result["columns"] == ["part_id", "part_name"]
    assert [r["part_id"] for r in result["rows"]] == ["TS-07"]


def test_default_limit_200(db_url):
    result = run_query("SELECT * FROM run_logs ORDER BY id", db_url)
    assert result["row_count"] == 200 and result["truncated"] is True
    assert result["rows"][0]["id"] == 1  # 정렬 순서 유지


def test_custom_limit_and_not_truncated(db_url):
    assert run_query("SELECT * FROM equipment", db_url, limit=5)["row_count"] == 5
    small = run_query("SELECT * FROM equipment", db_url, limit=50)
    assert small["row_count"] == 12 and small["truncated"] is False


def test_invalid_limit(db_url):
    with pytest.raises(UserError):
        run_query("SELECT 1", db_url, limit=0)


def test_alias_main_bearing_gives_two_br_candidates(db_url):
    result = run_query("SELECT part_id FROM parts WHERE aliases LIKE '%주축 베어링%' ORDER BY 1", db_url)
    assert [r["part_id"] for r in result["rows"]] == ["BR-01", "BR-02"]


def test_sql_error_is_user_error(db_url):
    with pytest.raises(UserError, match="SQL 실행 오류"):
        run_query("SELECT no_such_column FROM parts", db_url)


def test_readonly_connection_blocks_writes(db_url):
    """검증을 우회해도 읽기전용 연결이 쓰기를 막는다 (이중 안전장치)."""
    with read_connection(db_url) as conn:
        with pytest.raises(Exception, match="readonly"):
            conn.execute(text("DELETE FROM repair_logs"))


def test_schema_lists_tables(db_url):
    tables = get_schema(db_url)["tables"]
    assert "parts" in tables and "spec_tailstock" in tables
    fk = {c["column"]: c["fk"] for c in tables["parts"]}
    assert fk["assembly_code"] == "assemblies.assembly_code"


def test_missing_db_is_user_error(tmp_path):
    with pytest.raises(UserError, match="init_db"):
        run_query("SELECT 1", f"sqlite:///{(tmp_path / 'none.db').as_posix()}")
