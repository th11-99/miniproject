"""수리 이력 조회 (필터: 설비·파트·기간·돌발 여부). 최근 작업일·최근 등록 순.

  python scripts/history.py --equipment 3호기 --part BR-01 --from 2026-01-01 --breakdown yes
"""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from scripts import schema  # noqa: E402
from scripts.common import UserError, emit, read_connection, run_cli  # noqa: E402
from scripts.normalize import normalize_equipment  # noqa: E402

DEFAULT_LIMIT = 1000


def list_repairs(equipment: str | None = None, part: str | None = None, date_from: date | None = None,
                 date_to: date | None = None, breakdown: bool | None = None, limit: int = DEFAULT_LIMIT,
                 url: str | None = None) -> dict:
    if date_from and date_to and date_from > date_to:
        raise UserError("시작일이 종료일보다 늦습니다.")
    lg, p, a = schema.repair_logs.c, schema.parts.c, schema.assemblies.c
    stmt = (
        select(lg.id, lg.log_date, lg.equipment_id, lg.part_id, p.part_name, p.unit, a.name.label("assembly"),
               lg.action_type, lg.is_breakdown, lg.description, lg.created_at)
        .join(schema.parts, lg.part_id == p.part_id)
        .join(schema.assemblies, p.assembly_code == a.assembly_code)
        .order_by(lg.log_date.desc(), lg.id.desc())
    )
    if equipment:
        stmt = stmt.where(lg.equipment_id == normalize_equipment(equipment))
    if part:
        stmt = stmt.where(lg.part_id == part.strip().upper())
    if date_from:
        stmt = stmt.where(lg.log_date >= date_from)
    if date_to:
        stmt = stmt.where(lg.log_date <= date_to)
    if breakdown is not None:
        stmt = stmt.where(lg.is_breakdown == breakdown)
    with read_connection(url) as conn:
        rows = [dict(r._mapping) for r in conn.execute(stmt.limit(limit + 1))]
    return {"rows": rows[:limit], "row_count": min(len(rows), limit), "truncated": len(rows) > limit, "limit": limit}


def main() -> None:
    parser = argparse.ArgumentParser(description="수리 이력 조회")
    parser.add_argument("--equipment", help="설비 (예: CNC-03, 3호기)")
    parser.add_argument("--part", help="파트 ID (예: BR-01)")
    parser.add_argument("--from", dest="date_from", type=date.fromisoformat, help="시작일 YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", type=date.fromisoformat, help="종료일 YYYY-MM-DD")
    parser.add_argument("--breakdown", choices=("yes", "no"), help="yes=돌발만, no=예방만")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--format", choices=("json", "table"), default="json")
    args = parser.parse_args()
    breakdown = None if args.breakdown is None else args.breakdown == "yes"
    emit(list_repairs(args.equipment, args.part, args.date_from, args.date_to, breakdown, args.limit), args.format)


if __name__ == "__main__":
    sys.exit(run_cli(main))
