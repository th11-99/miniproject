"""교체 도래 점검 (기준일: 최근 가동로그일).

  python scripts/due_check.py --equipment 3호기 --unit TS --days 30 [--all] [--save]

상태: 초과(남은 양 ≤ 0) / 임박(N일 이내 도래) / 여유. 기본은 초과·임박만 보여주고 --all이면 여유까지.
"""

import argparse
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import schema  # noqa: E402
from scripts.common import ASSUMED_VALUE_NOTICE, ROOT, UserError, emit, read_connection, run_cli  # noqa: E402
from scripts.normalize import normalize_equipment  # noqa: E402
from scripts.usage import UsageData  # noqa: E402

STATUS_ORDER = {"초과": 0, "임박": 1, "여유": 2}
REPORTS_DIR = ROOT / "reports"


def due_check(equipment: str | None = None, unit: str | None = None, days: int = 30, include_all: bool = False,
              save: bool = False, url: str | None = None, out_dir: Path | None = None) -> dict:
    if days < 0:
        raise UserError("--days는 0 이상이어야 합니다.")
    if unit and unit not in schema.UNITS:
        raise UserError(f"유닛 코드는 {', '.join(schema.UNITS)} 중 하나입니다: {unit}")
    equipment = normalize_equipment(equipment) if equipment else None

    with read_connection(url) as conn:
        data = UsageData(conn)
    if data.ref_date is None:
        raise UserError("가동로그가 없어 도래를 계산할 수 없습니다.")
    ref = data.ref_date

    rows = [
        data.due(eq, pid, ref, days)
        for eq in sorted(data.installed) if equipment in (None, eq)
        for pid, part in data.parts.items() if unit in (None, part["unit"])
    ]
    summary = {s: sum(1 for r in rows if r["status"] == s) for s in STATUS_ORDER}
    if not include_all:
        rows = [r for r in rows if r["status"] != "여유"]
    rows.sort(key=lambda r: (STATUS_ORDER[r["status"]], r["days_left"] if r["days_left"] is not None else 10**9,
                             r["equipment_id"], r["part_id"]))

    result = {
        "reference_date": ref,
        "filters": {"equipment": equipment, "unit": unit, "days": days, "all": include_all},
        "summary": summary,
        "rows": rows,
        "notice": ASSUMED_VALUE_NOTICE,
    }
    if save:
        result["saved_to"] = str(_save_csv(rows, ref, out_dir or REPORTS_DIR))
    return result


CSV_COLUMNS = [
    ("status", "상태"), ("equipment_id", "설비"), ("part_id", "파트ID"), ("part_name", "파트명"), ("unit", "유닛"),
    ("assembly_code", "구조부"), ("basis", "기준"), ("interval_value", "교체주기"), ("last_replaced", "직전 교체"),
    ("usage", "사용량"), ("remaining", "남은 양"), ("usage_pct", "사용률(%)"), ("daily_avg", "일평균"),
    ("days_left", "남은 일수"), ("due_date", "예상 도래일"),
]


def csv_bytes(rows: list[dict]) -> bytes:
    """UTF-8 BOM CSV (엑셀에서 한글 깨짐 방지). 화면 다운로드와 --save가 같이 쓴다."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for _, label in CSV_COLUMNS])
    for r in rows:
        writer.writerow(["" if r[k] is None else r[k] for k, _ in CSV_COLUMNS])
    writer.writerow([])
    writer.writerow([ASSUMED_VALUE_NOTICE])
    return buf.getvalue().encode("utf-8-sig")


def _save_csv(rows: list[dict], ref, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"due_{ref.strftime('%Y%m%d')}.csv"
    path.write_bytes(csv_bytes(rows))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="교체 도래 점검 (기준일: 최근 가동로그일)")
    parser.add_argument("--equipment", help="설비 (예: CNC-03, 3호기)")
    parser.add_argument("--unit", choices=schema.UNITS, help="유닛 코드")
    parser.add_argument("--days", type=int, default=30, help="며칠 이내 도래분을 '임박'으로 볼지 (기본 30)")
    parser.add_argument("--all", action="store_true", help="'여유' 상태까지 모두 출력")
    parser.add_argument("--save", action="store_true", help="reports/due_YYYYMMDD.csv 저장")
    parser.add_argument("--format", choices=("json", "table"), default="json")
    args = parser.parse_args()
    result = due_check(args.equipment, args.unit, args.days, args.all, args.save)
    if args.format == "table":
        cols = ["status", "equipment_id", "part_id", "part_name", "usage_pct", "days_left", "due_date", "last_replaced"]
        result["rows"] = [{k: r[k] for k in cols} for r in result["rows"]]
    emit(result, args.format)


if __name__ == "__main__":
    sys.exit(run_cli(main))
