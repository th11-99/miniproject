"""설비·파트 마스터와 설비 상세(구조부 사양 + 장착 파트 도래 상태 + 최근 이력) 조회.

  python scripts/equipment.py --equipment 3호기
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from scripts import schema  # noqa: E402
from scripts.common import ASSUMED_VALUE_NOTICE, UserError, emit, read_connection, run_cli  # noqa: E402
from scripts.normalize import normalize_equipment  # noqa: E402
from scripts.usage import UsageData  # noqa: E402

# 사양 컬럼 → (표시 이름, 단위) — prd.md 5장 구조부 사양 테이블
SPEC_LABELS = {
    "gear_ranges": ("변속 단수", "단"), "gear_oil_grade": ("기어오일 등급", ""), "gear_oil_capacity_l": ("기어오일 용량", "L"),
    "spindle_max_rpm": ("최고 회전수", "rpm"), "spindle_nose": ("주축단 규격", ""), "spindle_motor_kw": ("주축 모터 출력", "kW"),
    "power_capacity_kva": ("전원 용량", "kVA"), "supply_voltage_v": ("전원 전압(3상)", "V"), "rated_current_a": ("정격 전류", "A"),
    "tool_stations": ("공구 스테이션", "개"), "index_time_sec": ("인덱싱 시간", "s"), "tool_shank_mm": ("공구 섕크", "mm"),
    "x_travel_mm": ("X축 이동량", "mm"), "x_rapid_m_min": ("X축 급이송", "m/min"), "x_ballscrew_dia_mm": ("X축 볼스크류 직경", "mm"),
    "z_travel_mm": ("Z축 이동량", "mm"), "z_rapid_m_min": ("Z축 급이송", "m/min"), "z_ballscrew_dia_mm": ("Z축 볼스크류 직경", "mm"),
    "quill_dia_mm": ("퀼 직경", "mm"), "quill_stroke_mm": ("퀼 스트로크", "mm"), "quill_taper": ("퀼 테이퍼", ""),
    "controller_model": ("컨트롤러", ""), "controlled_axes": ("제어 축 수", "축"), "usb_max_gb": ("USB 최대 용량", "GB"),
    "slant_angle_deg": ("베드 경사각", "°"), "guideway_type": ("습동면 방식", ""), "swing_over_bed_mm": ("베드 위 스윙", "mm"),
    "display_size_inch": ("화면 크기", "inch"), "is_touchscreen": ("터치스크린", ""), "has_mpg": ("MPG(수동 펄스 발생기)", ""),
}
RECENT_LOGS = 5


def _spec_value(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "있음" if value else "없음"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"
    return f"{value:,}" if isinstance(value, (int, float)) else str(value)


def equipment_list(url: str | None = None) -> list[dict]:
    with read_connection(url) as conn:
        return [dict(r._mapping) for r in conn.execute(select(schema.equipment).order_by(schema.equipment.c.equipment_id))]


def parts_list(url: str | None = None) -> list[dict]:
    p = schema.parts.c
    with read_connection(url) as conn:
        return [dict(r._mapping) for r in conn.execute(
            select(p.part_id, p.part_name, p.unit, p.assembly_code, p.stock_qty, p.safety_stock).order_by(p.part_id))]


def equipment_detail(equipment: str, url: str | None = None) -> dict:
    eq_id = normalize_equipment(equipment)
    with read_connection(url) as conn:
        eq = conn.execute(select(schema.equipment).where(schema.equipment.c.equipment_id == eq_id)).first()
        if eq is None:
            raise UserError(f"등록되지 않은 설비입니다: {eq_id}")
        assemblies = [dict(r._mapping) for r in conn.execute(select(schema.assemblies).order_by(schema.assemblies.c.sort_order))]
        specs = {}
        for code, table in schema.SPEC_TABLES.items():
            row = conn.execute(select(table).where(table.c.equipment_id == eq_id)).first()
            specs[code] = dict(row._mapping) if row else {}
        data = UsageData(conn)
    ref = data.ref_date

    result_assemblies = []
    for asm in assemblies:
        code = asm["assembly_code"]
        spec_items = [
            {"column": col, "label": SPEC_LABELS[col][0], "value": _spec_value(specs[code].get(col)), "unit": SPEC_LABELS[col][1]}
            for col in schema.SPEC_TABLES[code].columns.keys() if col in SPEC_LABELS
        ]
        part_ids = [pid for pid, p in data.parts.items() if p["assembly_code"] == code]
        due_rows = [data.due(eq_id, pid, ref, 30) for pid in part_ids] if ref else []
        logs = sorted((log for pid in part_ids for log in data.logs.get((eq_id, pid), [])),
                      key=lambda log: (log["log_date"], log["id"]), reverse=True)[:RECENT_LOGS]
        for log in logs:
            log["part_name"] = data.parts[log["part_id"]]["part_name"]
        result_assemblies.append({**asm, "specs": spec_items, "parts": due_rows, "recent_logs": logs})

    return {
        "equipment": dict(eq._mapping),
        "reference_date": ref,
        "assemblies": result_assemblies,
        "notice": ASSUMED_VALUE_NOTICE,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="설비 상세: 구조부 사양, 장착 파트 도래 상태, 최근 이력")
    parser.add_argument("--equipment", required=True, help="설비 (예: CNC-03, 3호기)")
    args = parser.parse_args()
    emit(equipment_detail(args.equipment))


if __name__ == "__main__":
    sys.exit(run_cli(main))
