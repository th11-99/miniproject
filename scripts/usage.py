"""사용량·교체 도래·판정 공통 로직 (log_repair, due_check, analyze가 함께 쓴다).

- 가동로그 누적값은 설비 도입 시점부터 센 값이다. 첫 가동로그 이전 날짜의 누적값은
  도입일(0)과 첫 가동로그를 잇는 직선으로 추정한다.
- 사용량 = 직전 "리셋 작업"(기본: 교체) 이후 누적값 증가분. 리셋 작업이 없으면 도입 이후 전체.
- 판정 기준은 prd.md 7장 "판정 기준"을 따른다.
"""

import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select

from scripts import schema

MONTH_DAYS = 30.4375
EARLY_FAILURE_RATIO = 0.5  # 조기고장: 사용량 < 교체주기의 50%
REPEAT_WINDOW_DAYS = 90  # 반복고장: 같은 설비·파트 돌발이 90일 내 재발
SPARE_DUE_DAYS = 30  # 예비품 부족: 30일 내 도래 수량과 비교
AVG_WINDOW_DAYS = 30  # 일평균 사용량 계산 구간

# 사용량을 0으로 되돌리는 작업. 소모성 유지 작업이 주기 작업인 파트는 예외로 둔다.
DEFAULT_RESET_ACTIONS = ("교체",)
RESET_ACTIONS = {
    "LB-01": ("교체", "보충"),  # 습동유는 보충이 주기 작업
    "EL-03": ("교체", "청소"),  # 판넬 쿨러 필터는 청소가 주기 작업
}

BASIS_UNIT = {"run_hours": "시간", "clamp_count": "회(클램핑)", "index_count": "회(인덱싱)", "months": "개월"}


def reset_actions(part_id: str) -> tuple[str, ...]:
    return RESET_ACTIONS.get(part_id, DEFAULT_RESET_ACTIONS)


def fmt_amount(value: float, basis: str) -> str:
    if basis == "months":
        return f"{value:.1f}{BASIS_UNIT[basis]}"
    return f"{value:,.0f}{BASIS_UNIT[basis]}"


# ---------- 판정 (순수 함수) ----------

def is_early_failure(usage: float, interval: float) -> bool:
    return usage < interval * EARLY_FAILURE_RATIO


def recent_breakdowns(previous_breakdowns: list[date], on: date) -> list[date]:
    """on 이전(당일 포함) 90일 안에 있었던 같은 설비·파트의 돌발 일자."""
    return [d for d in previous_breakdowns if 0 <= (on - d).days <= REPEAT_WINDOW_DAYS]


def spare_shortage(stock_after: int, safety_stock: int, due_soon: int) -> list[str]:
    """예비품 부족 사유 목록 (빈 목록 = 부족 아님)."""
    reasons = []
    if stock_after <= safety_stock:
        reasons.append(f"교체 후 재고 {stock_after}개가 안전재고 {safety_stock}개 이하")
    if stock_after < due_soon:
        reasons.append(f"교체 후 재고 {stock_after}개가 {SPARE_DUE_DAYS}일 내 교체 도래 {due_soon}대분보다 적음")
    return reasons


# ---------- 데이터 로딩 ----------

class UsageData:
    """사용량 계산에 필요한 설비·파트·가동로그·이력을 한 번에 읽어 메모리에서 계산한다."""

    def __init__(self, conn):
        self.installed = {r.equipment_id: r.installed_at for r in conn.execute(select(schema.equipment))}
        self.parts = {r.part_id: dict(r._mapping) for r in conn.execute(select(schema.parts))}

        self._dates: dict[str, list[date]] = defaultdict(list)
        self._values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        rl = schema.run_logs.c
        for r in conn.execute(select(rl.equipment_id, rl.log_date, rl.run_hours, rl.clamp_count, rl.index_count)
                              .order_by(rl.equipment_id, rl.log_date)):
            self._dates[r.equipment_id].append(r.log_date)
            for basis in ("run_hours", "clamp_count", "index_count"):
                self._values[r.equipment_id][basis].append(float(getattr(r, basis)))
        self.ref_date: date | None = max((d[-1] for d in self._dates.values()), default=None)

        self.logs: dict[tuple[str, str], list[dict]] = defaultdict(list)
        lg = schema.repair_logs.c
        for r in conn.execute(select(lg.id, lg.log_date, lg.equipment_id, lg.part_id, lg.action_type,
                                     lg.is_breakdown, lg.description).order_by(lg.log_date, lg.id)):
            self.logs[(r.equipment_id, r.part_id)].append(dict(r._mapping))

    # ----- 누적값 -----
    def counter(self, equipment_id: str, basis: str, on: date) -> float:
        dates = self._dates.get(equipment_id)
        installed = self.installed[equipment_id]
        if not dates or on <= installed:
            return 0.0
        values = self._values[equipment_id][basis]
        if on < dates[0]:  # 첫 가동로그 이전: 도입일(0)과 첫 로그를 잇는 직선
            return values[0] * (on - installed).days / max((dates[0] - installed).days, 1)
        return values[bisect_right(dates, on) - 1]

    def elapsed(self, equipment_id: str, basis: str, start: date | None, end: date) -> float:
        start = start or self.installed[equipment_id]
        if basis == "months":
            return max((end - start).days, 0) / MONTH_DAYS
        return max(self.counter(equipment_id, basis, end) - self.counter(equipment_id, basis, start), 0.0)

    def daily_rate(self, equipment_id: str, basis: str, ref: date) -> float:
        if basis == "months":
            return 1 / MONTH_DAYS
        start = ref - timedelta(days=AVG_WINDOW_DAYS)
        return self.elapsed(equipment_id, basis, start, ref) / AVG_WINDOW_DAYS

    # ----- 이력 -----
    def last_reset(self, equipment_id: str, part_id: str, before: date, inclusive: bool = True,
                   exclude_id: int | None = None) -> date | None:
        actions = reset_actions(part_id)
        found = None
        for log in self.logs.get((equipment_id, part_id), []):
            if log["id"] == exclude_id or log["action_type"] not in actions:
                continue
            if log["log_date"] < before or (inclusive and log["log_date"] == before):
                found = log["log_date"]
        return found

    def breakdown_dates(self, equipment_id: str, part_id: str, before: date, exclude_id: int | None = None) -> list[date]:
        return [log["log_date"] for log in self.logs.get((equipment_id, part_id), [])
                if log["is_breakdown"] and log["id"] != exclude_id and log["log_date"] <= before]

    # ----- 판정 -----
    def early_failure(self, equipment_id: str, part_id: str, on: date, exclude_id: int | None = None) -> dict | None:
        """on 일자의 돌발 교체·수리가 조기고장이면 근거를 돌려준다."""
        part = self.parts[part_id]
        last = self.last_reset(equipment_id, part_id, on, inclusive=False, exclude_id=exclude_id)
        if last is None:
            return None  # 이전 교체 기록이 없으면 판단하지 않는다 (도입 이후 원부품)
        used = self.elapsed(equipment_id, part["basis"], last, on)
        if not is_early_failure(used, part["interval_value"]):
            return None
        return {"last_reset": last, "usage": round(used, 2), "interval": part["interval_value"],
                "usage_pct": round(used / part["interval_value"] * 100, 1), "basis": part["basis"]}

    def repeat_failure(self, equipment_id: str, part_id: str, on: date, exclude_id: int | None = None) -> list[date]:
        """on 일자 돌발 이전 90일 안의 같은 설비·파트 돌발 일자 (exclude_id = 판정 대상 이력 자신)."""
        return recent_breakdowns(self.breakdown_dates(equipment_id, part_id, on, exclude_id), on)

    # ----- 도래 -----
    def due(self, equipment_id: str, part_id: str, ref: date, days: int) -> dict:
        part = self.parts[part_id]
        basis, interval = part["basis"], part["interval_value"]
        # 기준일 이후(오늘 등록분)에 한 교체도 반영한다
        last = self.last_reset(equipment_id, part_id, max(ref, date.today()))
        used = self.elapsed(equipment_id, basis, last, ref) if (last is None or last <= ref) else 0.0
        remaining = interval - used
        rate = self.daily_rate(equipment_id, basis, ref)
        days_left = remaining / rate if rate > 0 else None
        if remaining <= 0:
            status = "초과"
        elif days_left is not None and days_left <= days:
            status = "임박"
        else:
            status = "여유"
        return {
            "equipment_id": equipment_id,
            "part_id": part_id,
            "part_name": part["part_name"],
            "unit": part["unit"],
            "assembly_code": part["assembly_code"],
            "basis": basis,
            "interval_value": interval,
            "last_replaced": last,
            "usage": round(used, 1),
            "remaining": round(remaining, 1),
            "usage_pct": round(used / interval * 100, 1),
            "daily_avg": round(rate, 3),
            "days_left": None if days_left is None else math.floor(days_left),
            "due_date": None if days_left is None else ref + timedelta(days=math.floor(days_left)),
            "status": status,
        }

    def due_soon_count(self, part_id: str, ref: date, days: int = SPARE_DUE_DAYS) -> int:
        """days 안에 교체가 도래(초과 포함)하는 설비 대수."""
        return sum(1 for eq in self.installed if self.due(eq, part_id, ref, days)["status"] != "여유")
