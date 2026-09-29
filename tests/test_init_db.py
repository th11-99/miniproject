import pytest
from sqlalchemy import inspect

from scripts import schema
from scripts.common import UserError, fetch_all, read_connection
from scripts.init_db import SCENARIOS, build_database

EXPECTED_UNIT_COUNTS = {"HS": 5, "TS": 7, "SD": 7, "BR": 7, "LB": 6, "EL": 7}
# prd.md 3장 구조부 표 기준 베어링 장착 위치
EXPECTED_BEARING_ASSEMBLY = {
    "BR-01": "HDS", "BR-02": "HDS", "BR-03": "XSL", "BR-04": "CAR",
    "BR-05": "XSL", "BR-06": "CAR", "BR-07": "TUR",
}


def test_tables_created(db_url):
    with read_connection(db_url) as conn:
        tables = set(inspect(conn).get_table_names())
    assert {"equipment", "assemblies", "parts", "repair_logs", "run_logs", "schema_version"} <= tables
    assert {t.name for t in schema.SPEC_TABLES.values()} <= tables


def test_migration_recorded(db_url):
    with read_connection(db_url) as conn:
        versions = [r["version"] for r in fetch_all(conn, "SELECT version FROM schema_version")]
    assert versions == ["001_init"]


def test_equipment_12(db_url):
    with read_connection(db_url) as conn:
        ids = [r["equipment_id"] for r in fetch_all(conn, "SELECT equipment_id FROM equipment ORDER BY 1")]
    assert ids == [f"CNC-{n:02d}" for n in range(1, 13)]


def test_parts_39_and_id_ranges(db_url):
    with read_connection(db_url) as conn:
        rows = fetch_all(conn, "SELECT part_id, unit FROM parts")
    assert len(rows) == 39
    counts = {}
    for r in rows:
        assert r["part_id"][:2] == r["unit"]
        counts[r["unit"]] = counts.get(r["unit"], 0) + 1
    assert counts == EXPECTED_UNIT_COUNTS
    for unit, n in EXPECTED_UNIT_COUNTS.items():
        assert {r["part_id"] for r in rows if r["unit"] == unit} == {f"{unit}-{i:02d}" for i in range(1, n + 1)}


def test_assemblies_and_part_locations(db_url):
    with read_connection(db_url) as conn:
        codes = [r["assembly_code"] for r in fetch_all(conn, "SELECT assembly_code FROM assemblies ORDER BY sort_order")]
        parts = {r["part_id"]: r["assembly_code"] for r in fetch_all(conn, "SELECT part_id, assembly_code FROM parts")}
    assert codes == ["GBX", "HDS", "CTL", "TUR", "XSL", "CAR", "TLS", "NCU", "BED", "OPP"]
    assert all(parts.values())
    assert {pid: asm for pid, asm in parts.items() if pid.startswith("BR")} == EXPECTED_BEARING_ASSEMBLY


def test_bearings_always_br_unit(db_url):
    with read_connection(db_url) as conn:
        rows = fetch_all(conn, "SELECT part_id, unit FROM parts WHERE part_name LIKE '%베어링%'")
    assert rows and all(r["unit"] == "BR" for r in rows)


def test_spec_tables_three_columns_and_12_rows(db_url):
    with read_connection(db_url) as conn:
        insp = inspect(conn)
        for table in schema.SPEC_TABLES.values():
            cols = [c["name"] for c in insp.get_columns(table.name)]
            spec_cols = [c for c in cols if c not in ("equipment_id", "updated_at")]
            assert len(spec_cols) == 3, table.name
            n = fetch_all(conn, f"SELECT COUNT(*) AS n FROM {table.name}")[0]["n"]
            assert n == 12, table.name


def test_sample_history(db_url):
    with read_connection(db_url) as conn:
        repairs = fetch_all(conn, "SELECT COUNT(*) AS n FROM repair_logs")[0]["n"]
        runs = fetch_all(conn, "SELECT COUNT(*) AS n FROM run_logs")[0]["n"]
    assert repairs >= 150
    assert runs == 12 * 365


def test_scenarios_present(db_url):
    with read_connection(db_url) as conn:
        for _, eq, pid, action, breakdown, desc in SCENARIOS:
            rows = fetch_all(conn, "SELECT 1 FROM repair_logs WHERE equipment_id=:e AND part_id=:p AND description=:d",
                             {"e": eq, "p": pid, "d": desc})
            assert rows, (eq, pid, desc)


def test_run_logs_cumulative(db_url):
    with read_connection(db_url) as conn:
        rows = fetch_all(conn, "SELECT run_hours, clamp_count, index_count FROM run_logs "
                               "WHERE equipment_id='CNC-01' ORDER BY log_date")
    for prev, cur in zip(rows, rows[1:]):
        assert cur["run_hours"] >= prev["run_hours"]
        assert cur["clamp_count"] >= prev["clamp_count"]
        assert cur["index_count"] >= prev["index_count"]


def test_same_seed_same_data(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    from tests.conftest import END_DATE
    for p in (a, b):
        build_database(f"sqlite:///{p.as_posix()}", seed=7, end_date=END_DATE)
    sql = "SELECT log_date, equipment_id, part_id, action_type, is_breakdown, description FROM repair_logs ORDER BY id"
    with read_connection(f"sqlite:///{a.as_posix()}") as ca, read_connection(f"sqlite:///{b.as_posix()}") as cb:
        assert fetch_all(ca, sql) == fetch_all(cb, sql)


def test_refuses_non_sqlite():
    with pytest.raises(UserError, match="SQLite"):
        build_database("postgresql+psycopg://user:pw@localhost:5432/prod")
