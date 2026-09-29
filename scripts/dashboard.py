"""대시보드 요약: 교체 초과·30일 내 도래·이번 달 돌발·예방보전 비율, 설비별 상태."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.analyze import PM_RATIO_TARGET, analyze  # noqa: E402
from scripts.due_check import due_check  # noqa: E402
from scripts.equipment import equipment_list  # noqa: E402

DUE_DAYS = 30
PM_MONTHS = 6


def dashboard_summary(url: str | None = None) -> dict:
    due = due_check(days=DUE_DAYS, include_all=True, url=url)
    ana = analyze(months=PM_MONTHS, url=url)
    ref = due["reference_date"]
    this_month = next((m for m in ana["monthly_pm_ratio"] if m["month"] == ref.strftime("%Y-%m")), None)

    per_eq = {e["equipment_id"]: {**e, "초과": 0, "임박": 0} for e in equipment_list(url)}
    for r in due["rows"]:
        if r["status"] in ("초과", "임박"):
            per_eq[r["equipment_id"]][r["status"]] += 1
    for e in per_eq.values():
        e["status"] = "초과" if e["초과"] else "임박" if e["임박"] else "정상"

    return {
        "reference_date": ref,
        "overdue": due["summary"]["초과"],
        "due_soon": due["summary"]["임박"],
        "due_days": DUE_DAYS,
        "month": ref.strftime("%Y-%m"),
        "breakdowns_this_month": this_month["breakdown"] if this_month else 0,
        "pm_ratio": ana["summary"]["pm_ratio"],
        "pm_ratio_target": PM_RATIO_TARGET,
        "pm_months": PM_MONTHS,
        "equipment": list(per_eq.values()),
        "top_findings": ana["findings"][:3],
    }
