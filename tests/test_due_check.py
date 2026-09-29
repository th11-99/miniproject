from datetime import timedelta

import pytest

from scripts.common import ASSUMED_VALUE_NOTICE, UserError
from scripts.due_check import due_check
from tests.conftest import END_DATE


def test_reference_date_is_latest_run_log(db_url):
    assert due_check(url=db_url)["reference_date"] == END_DATE


def test_default_hides_ok_rows(db_url):
    result = due_check(url=db_url)
    assert result["rows"]
    assert all(r["status"] in ("초과", "임박") for r in result["rows"])
    assert result["notice"] == ASSUMED_VALUE_NOTICE


def test_all_rows_and_summary(db_url):
    result = due_check(include_all=True, url=db_url)
    assert len(result["rows"]) == 12 * 39
    assert sum(result["summary"].values()) == 12 * 39
    # 샘플 데이터가 현실적인 분포인지: 초과는 일부여야 한다
    assert 0 < result["summary"]["초과"] < 12 * 39 * 0.2


def test_status_consistency(db_url):
    for r in due_check(days=30, include_all=True, url=db_url)["rows"]:
        if r["status"] == "초과":
            assert r["remaining"] <= 0
        elif r["status"] == "임박":
            assert r["remaining"] > 0 and r["days_left"] <= 30
        else:
            assert r["days_left"] is None or r["days_left"] > 30
        if r["days_left"] is not None:
            assert r["due_date"] == END_DATE + timedelta(days=r["days_left"])


def test_sorted_overdue_first(db_url):
    statuses = [r["status"] for r in due_check(url=db_url)["rows"]]
    assert statuses == sorted(statuses, key={"초과": 0, "임박": 1}.get)


@pytest.mark.parametrize("equipment, unit", [("CNC-03", None), ("3호기", None), (None, "TS"), ("CNC-07", "TS")])
def test_filters(db_url, equipment, unit):
    rows = due_check(equipment=equipment, unit=unit, include_all=True, url=db_url)["rows"]
    assert rows
    if equipment:
        assert {r["equipment_id"] for r in rows} == {"CNC-03" if "3" in equipment else "CNC-07"}
    if unit:
        assert {r["unit"] for r in rows} == {unit}


def test_longer_window_finds_more(db_url):
    counts = [len(due_check(days=d, url=db_url)["rows"]) for d in (7, 30, 90)]
    assert counts == sorted(counts)


def test_last_replacement_used(db_url):
    row = next(r for r in due_check(equipment="CNC-05", include_all=True, url=db_url)["rows"] if r["part_id"] == "HS-04")
    assert row["last_replaced"] == END_DATE - timedelta(days=40)
    assert row["status"] == "여유"


def test_reset_by_supplement_for_way_oil(db_url):
    # 습동유(LB-01)는 보충이 주기 작업이라 보충이 직전 리셋이 된다
    rows = due_check(unit="LB", include_all=True, url=db_url)["rows"]
    assert all(r["last_replaced"] is not None for r in rows if r["part_id"] == "LB-01")


def test_save_csv_with_bom(db_url, tmp_path):
    result = due_check(save=True, url=db_url, out_dir=tmp_path)
    path = tmp_path / f"due_{END_DATE.strftime('%Y%m%d')}.csv"
    assert result["saved_to"] == str(path)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("상태,설비,파트ID")
    assert "데모용 가정값" in text


@pytest.mark.parametrize("kwargs", [{"days": -1}, {"unit": "XX"}, {"equipment": "13호기"}])
def test_invalid_filters(db_url, kwargs):
    with pytest.raises(UserError):
        due_check(url=db_url, **kwargs)
