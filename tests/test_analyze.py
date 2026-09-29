import json

import pytest

from scripts.analyze import analyze
from scripts.common import UserError
from tests.conftest import END_DATE

FINDING_KEYS = {"문제", "추정 원인", "권장 조치", "확인 방법", "근거", "심각도"}


@pytest.fixture(scope="module")
def result(db_url):
    return analyze(months=6, url=db_url)


def test_summary(result):
    s = result["summary"]
    assert s["total"] == s["breakdown"] + s["preventive"]
    assert 0 <= s["pm_ratio"] <= 100
    assert s["pm_ratio_target"] == 70.0
    assert s["parts_cost"] >= s["breakdown_parts_cost"] > 0


def test_breakdown_counts_consistent(result):
    total = result["summary"]["breakdown"]
    assert sum(result["breakdowns_by_equipment"].values()) == total
    assert sum(result["breakdowns_by_unit"].values()) == total
    assert sum(result["breakdowns_by_assembly"].values()) == total


def test_repeat_failures_include_scenarios(result):
    keys = {(r["equipment_id"], r["part_id"]) for r in result["repeat_failures"]}
    assert {("CNC-07", "TS-04"), ("CNC-02", "SD-02")} <= keys
    assert all(r["min_gap_days"] <= 90 for r in result["repeat_failures"])


def test_early_failures_include_scenarios(result):
    keys = {(e["equipment_id"], e["part_id"]) for e in result["early_failures"]}
    assert {("CNC-05", "HS-04"), ("CNC-09", "TS-07")} <= keys
    assert all(e["usage_pct"] < 50 for e in result["early_failures"])


def test_findings_shape(result):
    findings = result["findings"]
    assert findings
    for f in findings:
        assert set(f) == FINDING_KEYS
        assert f["추정 원인"].startswith("(추정)")
        assert f["확인 방법"]
    severities = [f["심각도"] for f in findings]
    assert severities == sorted(severities, key={"높음": 0, "중간": 1, "낮음": 2}.get)


def test_hydraulic_repeat_finding_mentions_pressure(result):
    f = next(f for f in result["findings"] if "TS-04" in f["문제"])
    assert "압력" in f["확인 방법"] or "전압" in f["확인 방법"]


def test_monthly_pm_ratio(result):
    months = result["monthly_pm_ratio"]
    assert months and all(0 <= m["pm_ratio"] <= 100 for m in months)
    assert [m["month"] for m in months] == sorted(m["month"] for m in months)


def test_period(result):
    assert result["reference_date"] == END_DATE
    assert result["period"]["to"] == END_DATE


def test_equipment_filter(db_url):
    r = analyze(months=12, equipment="7호기", url=db_url)
    assert set(r["breakdowns_by_equipment"]) <= {"CNC-07"}
    assert {x["equipment_id"] for x in r["repeat_failures"]} <= {"CNC-07"}


def test_longer_period_has_more_logs(db_url):
    assert analyze(months=12, url=db_url)["summary"]["total"] >= analyze(months=3, url=db_url)["summary"]["total"]


def test_low_pm_ratio_finding(db_url):
    # 한 달 범위 특정 설비는 비율이 낮을 수 있음 — 규칙 자체는 70% 미만이면 반드시 finding이 생긴다
    for months in (1, 2, 3, 6, 12):
        r = analyze(months=months, url=db_url)
        has = any("예방보전 비율" in f["문제"] for f in r["findings"])
        assert has == (r["summary"]["pm_ratio"] is not None and r["summary"]["pm_ratio"] < 70)


def test_save_json(db_url, tmp_path):
    r = analyze(save=True, url=db_url, out_dir=tmp_path)
    saved = json.loads((tmp_path / f"analysis_{END_DATE.strftime('%Y%m%d')}.json").read_text(encoding="utf-8"))
    assert saved["summary"] == r["summary"]
    assert saved["findings"]


def test_invalid_months(db_url):
    with pytest.raises(UserError):
        analyze(months=0, url=db_url)
