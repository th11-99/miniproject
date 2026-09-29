"""수리 이력 등록 — DB에 쓰는 유일한 경로.

항상 --dry-run 결과를 사용자에게 보여주고 승인받은 뒤 --dry-run 없이 다시 실행한다.

  python scripts/log_repair.py --equipment 3호기 --part BR-01 --action 교체 --breakdown --desc "소음 발생" --dry-run

info 판정 (prd.md 7장):
  조기고장     돌발 교체·수리 시점 사용량 < 교체주기의 50%
  반복고장     같은 설비·파트 돌발이 90일 내 재발
  예비품 부족  교체 후 재고 ≤ 안전재고, 또는 30일 내 교체 도래 대수보다 적음
  중복 의심    같은 날·설비·파트·조치 이력이 이미 있음
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import insert, select, update  # noqa: E402

from scripts import schema  # noqa: E402
from scripts.common import UserError, emit, get_engine, read_connection, run_cli  # noqa: E402
from scripts.normalize import normalize_equipment  # noqa: E402
from scripts.usage import REPEAT_WINDOW_DAYS, SPARE_DUE_DAYS, UsageData, fmt_amount, spare_shortage  # noqa: E402


def _parse_date(value) -> date:
    if not value:
        return date.today()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise UserError(f"날짜 형식이 잘못되었습니다: {value} (예: 2026-09-29)") from exc


def build_row(conn, equipment: str, part: str, action: str, breakdown: bool, log_date: date, desc: str) -> dict:
    if action not in schema.ACTION_TYPES:
        raise UserError(f"조치 유형은 {' / '.join(schema.ACTION_TYPES)} 중 하나여야 합니다: {action}")
    equipment = normalize_equipment(equipment)
    part = part.strip().upper()
    eq = conn.execute(select(schema.equipment.c.name).where(schema.equipment.c.equipment_id == equipment)).first()
    if eq is None:
        raise UserError(f"등록되지 않은 설비입니다: {equipment} (CNC-01 ~ CNC-12)")
    p = conn.execute(select(schema.parts).where(schema.parts.c.part_id == part)).first()
    if p is None:
        raise UserError(f"등록되지 않은 파트ID입니다: {part}. normalize.py나 query.py로 별칭을 먼저 조회하세요.")
    return {
        "log_date": log_date,
        "equipment_id": equipment,
        "equipment_name": eq.name,
        "part_id": part,
        "part_name": p.part_name,
        "unit": p.unit,
        "assembly_code": p.assembly_code,
        "action_type": action,
        "is_breakdown": breakdown,
        "description": desc,
        "stock_before": p.stock_qty,
        "stock_after": max(p.stock_qty - 1, 0) if action == "교체" else p.stock_qty,
    }


def judge(conn, row: dict) -> list[dict]:
    """등록하려는 행에 대한 경고(info) 목록."""
    data = UsageData(conn)
    eq, pid, on = row["equipment_id"], row["part_id"], row["log_date"]
    part = data.parts[pid]
    info = []

    if row["is_breakdown"] and row["action_type"] in ("교체", "수리"):
        early = data.early_failure(eq, pid, on)
        if early:
            info.append({
                "type": "조기고장",
                "message": (f"직전 교체({early['last_reset']}) 이후 사용량 {fmt_amount(early['usage'], early['basis'])} — "
                            f"교체주기 {fmt_amount(early['interval'], early['basis'])}의 {early['usage_pct']}% (기준 50% 미만). "
                            "부품 품질·장착 상태·사용 조건을 확인하세요."),
                "detail": early,
            })

    if row["is_breakdown"]:
        previous = data.repeat_failure(eq, pid, on)
        if previous:
            dates = ", ".join(d.isoformat() for d in previous)
            info.append({
                "type": "반복고장",
                "message": f"같은 설비·파트의 돌발고장이 {REPEAT_WINDOW_DAYS}일 안에 또 발생했습니다 (이전: {dates}). 근본 원인 점검이 필요합니다.",
                "detail": {"previous_breakdowns": previous},
            })

    if row["action_type"] == "교체":
        ref = data.ref_date or on
        due_soon = data.due_soon_count(pid, ref)
        reasons = spare_shortage(row["stock_after"], part["safety_stock"], due_soon)
        if row["stock_before"] == 0:
            reasons.insert(0, "현재 재고가 0개입니다. 재고 데이터를 확인하세요")
        if reasons:
            info.append({
                "type": "예비품 부족",
                "message": f"{row['part_name']}({pid}) 예비품 부족: " + "; ".join(reasons) + ". 발주를 검토하세요.",
                "detail": {"stock_before": row["stock_before"], "stock_after": row["stock_after"],
                           "safety_stock": part["safety_stock"], f"due_within_{SPARE_DUE_DAYS}d": due_soon},
            })

    same = [log for log in data.logs.get((eq, pid), [])
            if log["log_date"] == on and log["action_type"] == row["action_type"]]
    if same:
        info.append({
            "type": "중복 의심",
            "message": f"같은 날 같은 설비·파트·조치 이력이 이미 {len(same)}건 있습니다 (ID {', '.join(str(s['id']) for s in same)}). 중복 등록이 아닌지 확인하세요.",
            "detail": {"existing_ids": [s["id"] for s in same]},
        })
    return info


def _insert(conn, row: dict) -> int:
    values = {k: row[k] for k in ("log_date", "equipment_id", "part_id", "action_type", "is_breakdown", "description")}
    return conn.execute(insert(schema.repair_logs).values(**values)).inserted_primary_key[0]


def _deduct_stock(conn, part_id: str) -> None:
    p = schema.parts.c
    conn.execute(update(schema.parts).where(p.part_id == part_id, p.stock_qty > 0).values(stock_qty=p.stock_qty - 1))


def log_repair(equipment: str, part: str, action: str, breakdown: bool = False, log_date=None,
               desc: str = "", dry_run: bool = True, url: str | None = None) -> dict:
    """dry_run=True(기본)는 DB를 바꾸지 않는다. False면 이력 추가와 재고 차감을 한 트랜잭션으로 처리한다."""
    d = _parse_date(log_date)
    if dry_run:
        with read_connection(url) as conn:
            row = build_row(conn, equipment, part, action, breakdown, d, desc)
            info = judge(conn, row)
        return {"dry_run": True, "row": row, "info": info}

    engine = get_engine(url)
    try:
        with engine.begin() as conn:  # 예외가 나면 이력·재고 모두 롤백
            row = build_row(conn, equipment, part, action, breakdown, d, desc)
            info = judge(conn, row)
            new_id = _insert(conn, row)
            if action == "교체":
                _deduct_stock(conn, row["part_id"])
    finally:
        engine.dispose()
    return {"dry_run": False, "id": new_id, "row": row, "info": info}


def main() -> None:
    parser = argparse.ArgumentParser(description="수리 이력 등록 (반드시 --dry-run 확인 후 승인받아 실행)")
    parser.add_argument("--equipment", required=True, help="설비 (예: CNC-03, 3호기)")
    parser.add_argument("--part", required=True, help="파트 ID (예: BR-01)")
    parser.add_argument("--action", required=True, choices=schema.ACTION_TYPES, help="조치 유형")
    parser.add_argument("--breakdown", action="store_true", help="돌발고장 대응이면 지정 (예방·정기 작업이면 생략)")
    parser.add_argument("--date", help="작업일 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--desc", default="", help="작업 내용")
    parser.add_argument("--dry-run", action="store_true", help="DB를 바꾸지 않고 등록될 내용과 경고만 확인")
    parser.add_argument("--format", choices=("json", "table"), default="json")
    args = parser.parse_args()

    result = log_repair(args.equipment, args.part, args.action, args.breakdown, args.date, args.desc,
                        dry_run=args.dry_run)
    if args.format == "table":
        result = {**result, "rows": [result.pop("row")]}
    emit(result, args.format)


if __name__ == "__main__":
    sys.exit(run_cli(main))
