"""샘플 DB 재생성 (로컬·테스트 전용).

기존 DB를 삭제하므로 --yes 가 있어야 실행된다. SQLite가 아닌 URL(운영 DB)은 무조건 거부한다.
생성되는 가동로그·수리이력은 데모용 가정 데이터다.

  python scripts/init_db.py --yes
"""

import argparse
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, insert, select  # noqa: E402

from scripts import master_data, schema  # noqa: E402
from scripts.common import UserError, emit, get_database_url, get_engine, is_sqlite, run_cli, sqlite_path  # noqa: E402
from scripts.migrate_lib import apply_pending  # noqa: E402
from scripts.usage import MONTH_DAYS  # noqa: E402

DAYS = 365

# ---------- 가동로그 ----------

def _run_logs(rng: random.Random, end: date) -> list[dict]:
    """설비별 일별 누적 가동로그. 누적값은 설비 도입 시점부터 센 값이다."""
    start = end - timedelta(days=DAYS - 1)
    rows = []
    for eq in master_data.EQUIPMENT:
        years = (start - eq["installed_at"]).days / 365
        hours = round(years * rng.uniform(2800, 3600), 1)
        clamps = int(hours * rng.uniform(80, 120))
        indexes = int(clamps * rng.uniform(4, 6))
        for i in range(DAYS):
            day = start + timedelta(days=i)
            if day.weekday() == 6:  # 일요일 휴무
                h = 0.0
            else:
                h = round(rng.uniform(10, 20), 1)
                if rng.random() < 0.03:  # 가끔 장시간 정지
                    h = round(rng.uniform(0, 4), 1)
            c = int(h * rng.uniform(60, 140))
            hours = round(hours + h, 1)
            clamps += c
            indexes += int(c * rng.uniform(3, 7))
            rows.append(dict(log_date=day, equipment_id=eq["equipment_id"],
                             run_hours=hours, clamp_count=clamps, index_count=indexes))
    return rows


# ---------- 수리이력 ----------

PM_TEXT = ["정기 PM {a}", "주기 도래로 {a}", "예방 {a}", "정기 점검 중 {a}"]
BREAKDOWN_TEXT = {
    "교체": ["{p} 파손으로 교체", "알람 발생, {p} 교체", "{p} 불량으로 교체"],
    "수리": ["{p} 누유 발생 수리", "{p} 작동 불량 수리", "설비 정지, {p} 수리"],
    "조정": ["가공 불량 발생, {p} 조정", "알람 발생 후 {p} 조정"],
    "점검": ["알람 발생, {p} 점검", "정지 발생 후 {p} 점검"],
}
ROUTINE_TEXT = {
    "점검": ["{p} 소음 점검", "{p} 상태 점검"],
    "청소": ["{p} 청소", "칩 누적으로 {p} 청소"],
    "조정": ["{p} 유격 조정"],
    "보충": ["{p} 보충"],
}

# 계획 작업 대상: (part_id, 조치, 주기(일))
PM_PLAN = [("LB-01", "보충", 90), ("EL-03", "청소", 90), ("TS-02", "교체", 180)]

# 의도적으로 넣는 판정 검증용 사례 (end 기준 며칠 전, 설비, 파트, 조치, 돌발, 설명)
SCENARIOS = [
    # 조기고장: 교체 후 사용량이 주기의 50% 미만에서 돌발 교체
    (200, "CNC-05", "HS-04", "교체", False, "정기 PM 교체"),
    (40, "CNC-05", "HS-04", "교체", True, "스핀들 구동벨트 파손으로 교체, 알람 발생"),
    (150, "CNC-09", "TS-07", "교체", False, "주기 도래로 교체"),
    (20, "CNC-09", "TS-07", "교체", True, "회전센터 소음·진동 불량으로 교체"),
    # 반복고장: 같은 설비·파트 돌발이 90일 내 재발
    (85, "CNC-07", "TS-04", "수리", True, "솔밸브 작동 불량 수리"),
    (35, "CNC-07", "TS-04", "수리", True, "솔밸브 작동 불량 재발, 수리"),
    (130, "CNC-02", "SD-02", "수리", True, "터렛 클램프 씰 누유 발생 수리"),
    (75, "CNC-02", "SD-02", "교체", True, "터렛 클램프 씰 누유 재발, 교체"),
    (18, "CNC-02", "SD-02", "교체", True, "공구대 클램프 누유, 씰 교체"),
]
SCENARIO_KEYS = {(eq, pid) for _, eq, pid, *_ in SCENARIOS}


def _baseline_day(rng: random.Random, end: date, part: dict, installed: date, logs: list[dict]) -> date | None:
    """기준일(end)에 교체주기의 15~108%를 쓴 상태가 되도록 직전 교체일을 역산한다. 원부품이면 None."""
    used = rng.uniform(0.15, 1.08) * part["interval_value"]
    basis = part["basis"]
    if basis == "months":
        day = end - timedelta(days=round(used * MONTH_DAYS))
    else:
        target = logs[-1][basis] - used
        if target <= 0:
            return None
        if target >= logs[0][basis]:
            day = next(r["log_date"] for r in logs if r[basis] >= target)
        else:  # 첫 가동로그 이전: 도입일(0)과 첫 로그를 잇는 직선 (usage.UsageData.counter와 같은 가정)
            day = installed + timedelta(days=int((logs[0]["log_date"] - installed).days * target / logs[0][basis]))
    return day if day > installed else None


def _repair_logs(rng: random.Random, end: date, run_rows: list[dict]) -> list[dict]:
    start = end - timedelta(days=DAYS - 1)
    names = {p["part_id"]: p["part_name"] for p in master_data.PARTS}
    rows = []

    def add(day, eq, pid, action, breakdown, desc):
        rows.append(dict(log_date=day, equipment_id=eq, part_id=pid, action_type=action,
                         is_breakdown=breakdown, description=desc))

    # 0) 설비×파트별 직전 교체 이력. 없으면 모든 파트가 도입 이후 사용량으로 계산돼 전부 초과가 된다
    runs_by_eq = defaultdict(list)
    for r in run_rows:
        runs_by_eq[r["equipment_id"]].append(r)
    for eq in master_data.EQUIPMENT:
        eq_id = eq["equipment_id"]
        for part in master_data.PARTS:
            if (eq_id, part["part_id"]) in SCENARIO_KEYS:
                continue  # 시나리오는 자체 이력만 사용
            day = _baseline_day(rng, end, part, eq["installed_at"], runs_by_eq[eq_id])
            if day is not None:
                desc = rng.choice(PM_TEXT).format(a="교체") if day >= start else "이전 교체 이력 (데모 초기값)"
                add(day, eq_id, part["part_id"], "교체", False, desc)

    # 1) 계획 작업: 주기마다 반복하되 일부 설비는 마지막 회차를 건너뛰어 주기 초과 상태를 만든다
    for eq in master_data.EQUIPMENT:
        for pid, action, cycle in PM_PLAN:
            day = start + timedelta(days=rng.randint(0, cycle - 1))
            while day <= end:
                if not (day > end - timedelta(days=cycle) and rng.random() < 0.25):
                    add(day, eq["equipment_id"], pid, action, False, rng.choice(PM_TEXT).format(a=action))
                day += timedelta(days=cycle + rng.randint(-10, 10))

    # 2) 비정기 작업 (돌발 + 일상 점검·청소)
    part_ids = [p["part_id"] for p in master_data.PARTS]
    for _ in range(70):
        eq = rng.choice(master_data.EQUIPMENT)["equipment_id"]
        pid = rng.choice(part_ids)
        if (eq, pid) in SCENARIO_KEYS:
            continue
        day = start + timedelta(days=rng.randint(0, DAYS - 1))
        if rng.random() < 0.55:
            action = rng.choice(list(BREAKDOWN_TEXT))
            add(day, eq, pid, action, True, rng.choice(BREAKDOWN_TEXT[action]).format(p=names[pid]))
        else:
            action = rng.choice(list(ROUTINE_TEXT))
            add(day, eq, pid, action, False, rng.choice(ROUTINE_TEXT[action]).format(p=names[pid]))

    # 3) 판정 검증용 사례
    for days_ago, eq, pid, action, breakdown, desc in SCENARIOS:
        add(end - timedelta(days=days_ago), eq, pid, action, breakdown, desc)

    rows.sort(key=lambda r: (r["log_date"], r["equipment_id"], r["part_id"]))
    return rows


# ---------- DB 생성 ----------

def seed_sample_data(conn, seed: int = 42, end_date: date | None = None) -> dict:
    """빈 스키마에 마스터 + 샘플 데이터를 넣는다. 테스트에서 PostgreSQL에도 같은 데이터를 넣을 때 쓴다."""
    rng = random.Random(seed)
    end = end_date or date.today() - timedelta(days=1)  # 최근 가동로그일 = 어제
    conn.execute(insert(schema.equipment), master_data.EQUIPMENT)
    conn.execute(insert(schema.assemblies), master_data.ASSEMBLY_ROWS)
    conn.execute(insert(schema.parts), master_data.PARTS)
    for eq in master_data.EQUIPMENT:
        for code, row in master_data.spec_rows(eq["equipment_id"]).items():
            conn.execute(insert(schema.SPEC_TABLES[code]), row)
    run_rows = _run_logs(rng, end)
    conn.execute(insert(schema.run_logs), run_rows)
    conn.execute(insert(schema.repair_logs), _repair_logs(rng, end, run_rows))

    def count(table):
        return conn.execute(select(func.count()).select_from(table)).scalar_one()

    return {
        "last_run_log_date": end.isoformat(),
        "counts": {t: count(schema.metadata.tables[t]) for t in
                   ("equipment", "assemblies", "parts", "run_logs", "repair_logs")},
        "spec_tables": len(schema.SPEC_TABLES),
        "notice": "샘플 데이터(가동로그·이력·교체주기·단가·사양)는 데모용 가정값입니다.",
    }


def build_database(url: str, seed: int = 42, end_date: date | None = None) -> dict:
    """스키마 생성 + 샘플 데이터 입력. url의 SQLite 파일을 새로 만든다."""
    if not is_sqlite(url):
        raise UserError("init_db.py는 로컬 SQLite 전용입니다. 운영 DB(PostgreSQL 등)에는 실행할 수 없습니다.")
    path = sqlite_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            path.unlink()
        except PermissionError as exc:
            raise UserError(f"DB 파일이 사용 중이라 지울 수 없습니다: {path}. Streamlit 앱 등 DB를 연 프로그램을 종료한 뒤 다시 실행하세요.") from exc

    engine = get_engine(url)
    try:
        with engine.begin() as conn:
            applied = apply_pending(conn)
            return {"db": str(path), "migrations": applied, **seed_sample_data(conn, seed, end_date)}
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="샘플 DB 재생성 (기존 DB 삭제, 로컬 SQLite 전용)")
    parser.add_argument("--yes", action="store_true", help="기존 DB 삭제에 동의")
    parser.add_argument("--seed", type=int, default=42, help="샘플 데이터 난수 시드 (기본 42)")
    args = parser.parse_args()

    url = get_database_url()
    if not is_sqlite(url):
        raise UserError("DATABASE_URL이 SQLite가 아닙니다. init_db.py는 운영 DB에 실행할 수 없습니다.")
    path = sqlite_path(url)
    if path.exists() and not args.yes:
        raise UserError(f"기존 DB가 있습니다: {path}\n삭제 후 다시 만들려면 --yes 를 붙여 실행하세요. (모든 이력이 사라집니다)")
    emit(build_database(url, seed=args.seed))


if __name__ == "__main__":
    sys.exit(run_cli(main))
