from datetime import timedelta

import pytest

from scripts import log_repair as lr
from scripts.common import UserError, fetch_all, read_connection
from scripts.log_repair import log_repair
from scripts.usage import is_early_failure, recent_breakdowns, spare_shortage
from tests.conftest import END_DATE


def _count(url, table="repair_logs"):
    with read_connection(url) as conn:
        return fetch_all(conn, f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


def _stock(url, part_id):
    with read_connection(url) as conn:
        return fetch_all(conn, "SELECT stock_qty FROM parts WHERE part_id = :p", {"p": part_id})[0]["stock_qty"]


def _types(result):
    return {i["type"] for i in result["info"]}


# ---------- 판정 규칙 (순수 함수) ----------

def test_early_failure_threshold():
    assert is_early_failure(3999, 8000)
    assert not is_early_failure(4000, 8000)


def test_recent_breakdowns_window():
    on = END_DATE
    dates = [on - timedelta(days=d) for d in (0, 30, 90, 91, 200)]
    assert recent_breakdowns(dates, on) == dates[:3]


@pytest.mark.parametrize("stock_after, safety, due, short", [
    (0, 1, 0, True), (1, 1, 0, True), (2, 1, 0, False), (2, 1, 3, True), (3, 1, 3, False),
])
def test_spare_shortage_rule(stock_after, safety, due, short):
    assert bool(spare_shortage(stock_after, safety, due)) is short


# ---------- dry-run ----------

def test_dry_run_does_not_write(db_url):
    before = (_count(db_url), _stock(db_url, "BR-01"))
    result = log_repair("CNC-03", "BR-01", "교체", breakdown=True, log_date=END_DATE, desc="소음", url=db_url)
    assert result["dry_run"] is True
    assert result["row"]["assembly_code"] == "HDS"
    assert (_count(db_url), _stock(db_url, "BR-01")) == before


def test_default_date_is_today(db_url):
    from datetime import date
    assert log_repair("CNC-03", "HS-02", "점검", url=db_url)["row"]["log_date"] == date.today()


def test_equipment_alias_accepted(db_url):
    assert log_repair("3호기", "hs-02", "점검", log_date=END_DATE, url=db_url)["row"]["equipment_id"] == "CNC-03"


def test_early_failure_only(db_url):
    # CNC-05 HS-04: END-200 예방 교체 → END-100 시점 돌발 교체면 사용량이 주기의 50% 미만, 이전 돌발 없음
    result = log_repair("CNC-05", "HS-04", "교체", breakdown=True, log_date=END_DATE - timedelta(days=100), url=db_url)
    early = next(i for i in result["info"] if i["type"] == "조기고장")
    assert early["detail"]["last_reset"] == END_DATE - timedelta(days=200)
    assert early["detail"]["usage_pct"] < 50
    assert "반복고장" not in _types(result)


def test_early_and_repeat(db_url):
    # CNC-05 HS-04: END-40 돌발 교체 직후 또 돌발
    result = log_repair("CNC-05", "HS-04", "교체", breakdown=True, log_date=END_DATE, url=db_url)
    assert {"조기고장", "반복고장"} <= _types(result)


def test_repeat_failure(db_url):
    # CNC-07 TS-04: END-35 돌발 수리 → 재발
    result = log_repair("CNC-07", "TS-04", "수리", breakdown=True, log_date=END_DATE, url=db_url)
    repeat = next(i for i in result["info"] if i["type"] == "반복고장")
    assert END_DATE - timedelta(days=35) in repeat["detail"]["previous_breakdowns"]
    assert "조기고장" not in _types(result)  # 도입 이후 원부품이라 조기고장 아님


def test_no_repeat_after_90_days(db_url):
    # CNC-07 TS-04 마지막 돌발(END-35)로부터 91일 뒤
    result = log_repair("CNC-07", "TS-04", "수리", breakdown=True, log_date=END_DATE + timedelta(days=56), url=db_url)
    assert "반복고장" not in _types(result)


def test_preventive_work_has_no_failure_info(db_url):
    result = log_repair("CNC-05", "HS-04", "교체", breakdown=False, log_date=END_DATE, url=db_url)
    assert not {"조기고장", "반복고장"} & _types(result)


def test_spare_shortage_zero_stock(db_url):
    result = log_repair("CNC-03", "BR-01", "교체", log_date=END_DATE, url=db_url)
    shortage = next(i for i in result["info"] if i["type"] == "예비품 부족")
    assert shortage["detail"]["stock_before"] == 0 and shortage["detail"]["stock_after"] == 0


def test_spare_shortage_below_safety(db_url):
    result = log_repair("CNC-03", "TS-02", "교체", log_date=END_DATE, url=db_url)  # 재고 1, 안전재고 2
    assert "예비품 부족" in _types(result)


def test_no_shortage_for_non_replacement(db_url):
    assert "예비품 부족" not in _types(log_repair("CNC-03", "BR-01", "점검", log_date=END_DATE, url=db_url))


def test_duplicate_suspected(db_url):
    with read_connection(db_url) as conn:
        row = fetch_all(conn, "SELECT log_date, equipment_id, part_id, action_type FROM repair_logs "
                              "WHERE equipment_id = 'CNC-07' AND part_id = 'TS-04' ORDER BY log_date DESC")[0]
    result = log_repair(row["equipment_id"], row["part_id"], row["action_type"], breakdown=True,
                        log_date=str(row["log_date"]), url=db_url)
    assert "중복 의심" in _types(result)


@pytest.mark.parametrize("kwargs, message", [
    ({"equipment": "CNC-13", "part": "BR-01", "action": "교체"}, "관리 대상"),
    ({"equipment": "CNC-03", "part": "BR-99", "action": "교체"}, "파트ID"),
    ({"equipment": "CNC-03", "part": "BR-01", "action": "교환"}, "조치 유형"),
    ({"equipment": "CNC-03", "part": "BR-01", "action": "교체", "log_date": "2026-13-01"}, "날짜"),
])
def test_rejects_invalid_input(db_url, kwargs, message):
    with pytest.raises(UserError, match=message):
        log_repair(**kwargs, url=db_url)


# ---------- 실제 등록 ----------

def test_real_write_replacement_deducts_stock(writable_db_url):
    url = writable_db_url
    before_count, before_stock = _count(url), _stock(url, "BR-02")
    result = log_repair("CNC-03", "BR-02", "교체", breakdown=True, log_date=END_DATE, desc="소음", dry_run=False, url=url)
    assert result["dry_run"] is False and result["id"]
    assert _count(url) == before_count + 1
    assert _stock(url, "BR-02") == before_stock - 1
    with read_connection(url) as conn:
        saved = fetch_all(conn, "SELECT equipment_id, part_id, action_type, is_breakdown, description "
                                "FROM repair_logs WHERE id = :i", {"i": result["id"]})[0]
    assert (saved["equipment_id"], saved["part_id"], saved["action_type"], bool(saved["is_breakdown"]),
            saved["description"]) == ("CNC-03", "BR-02", "교체", True, "소음")


def test_real_write_non_replacement_keeps_stock(writable_db_url):
    before = _stock(writable_db_url, "HS-02")
    log_repair("CNC-03", "HS-02", "점검", log_date=END_DATE, dry_run=False, url=writable_db_url)
    assert _stock(writable_db_url, "HS-02") == before


def test_zero_stock_not_negative(writable_db_url):
    log_repair("CNC-03", "BR-01", "교체", log_date=END_DATE, dry_run=False, url=writable_db_url)
    assert _stock(writable_db_url, "BR-01") == 0


def test_rollback_when_stock_update_fails(writable_db_url, monkeypatch):
    url = writable_db_url
    before = (_count(url), _stock(url, "BR-02"))

    def boom(conn, part_id):
        raise RuntimeError("재고 차감 실패")

    monkeypatch.setattr(lr, "_deduct_stock", boom)
    with pytest.raises(RuntimeError):
        log_repair("CNC-03", "BR-02", "교체", log_date=END_DATE, dry_run=False, url=url)
    assert (_count(url), _stock(url, "BR-02")) == before


def test_invalid_input_writes_nothing(writable_db_url):
    before = _count(writable_db_url)
    with pytest.raises(UserError):
        log_repair("CNC-03", "XX-01", "교체", dry_run=False, url=writable_db_url)
    assert _count(writable_db_url) == before
