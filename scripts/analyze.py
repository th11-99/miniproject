"""고장 패턴 분석 (기준일: 최근 가동로그일).

  python scripts/analyze.py --months 6 --equipment 3호기 [--save]

findings는 규칙 기반 해석이다: 문제 → 추정 원인 → 권장 조치 → 확인 방법.
원인은 어디까지나 "추정"이며 확인 방법으로 검증해야 한다.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from scripts import schema  # noqa: E402
from scripts.common import ROOT, UserError, emit, json_default, read_connection, run_cli  # noqa: E402
from scripts.normalize import normalize_equipment  # noqa: E402
from scripts.usage import MONTH_DAYS, REPEAT_WINDOW_DAYS, UsageData, fmt_amount  # noqa: E402

PM_RATIO_TARGET = 70.0  # prd.md 7장 성공 지표
REPORTS_DIR = ROOT / "reports"
UNIT_NAMES = {"HS": "주축대", "TS": "심압대", "SD": "새들", "BR": "베어링류", "LB": "윤활라인", "EL": "전기판넬"}
ASSEMBLY_NAMES = {"GBX": "기어박스", "HDS": "주축대", "CTL": "제어장치", "TUR": "공구대", "XSL": "이송대",
                  "CAR": "왕복대", "TLS": "심압대", "NCU": "NC장치", "BED": "베드", "OPP": "운전조작반"}
SEVERITY_ORDER = {"높음": 0, "중간": 1, "낮음": 2}

# 유닛별 기본 해석, 파트별 해석이 있으면 우선. (추정 원인, 권장 조치, 확인 방법)
UNIT_RULES = {
    "TS": ("작동유 오염·열화, 유압 필터 막힘, 설정 압력 이상",
           "유압 필터 교체, 작동유 성상 분석 후 교환, 설정 압력 재조정",
           "유압 압력 측정(설정압 대비), 작동유 오염도(NAS 등급)·색상 확인, 필터 차압 확인"),
    "SD": ("칩·절삭유 침투, 습동부 윤활 부족, 충돌 이력",
           "와이퍼·커버 점검, 윤활 상태 복구, 충돌 이력 확인",
           "백래시 측정, 서보 부하율 확인, 커버·와이퍼 육안 점검"),
    "HS": ("척 압력 이상, 벨트 장력 부족·풀리 정렬 불량, 칩 끼임",
           "척 압력·조 상태 점검, 벨트 장력 조정",
           "척 파지력 측정, 벨트 장력계 측정, 풀리 정렬 확인"),
    "BR": ("윤활 부족·오염, 과부하·충돌, 장착 정렬 불량",
           "윤활 상태 복구, 예압·정렬 점검 후 교체",
           "진동 측정(가속도·FFT), 베어링 온도 측정, 윤활유 상태 확인"),
    "LB": ("윤활 배관 막힘·누유, 분배기 불량, 습동유 부족",
           "배관·분배기 점검, 윤활 필터 교체, 습동유 보충 주기 재설정",
           "배관 누유 점검, 분배기 토출량 확인, 윤활 압력 확인"),
    "EL": ("판넬 내부 온도 상승, 먼지 유입, 전원 품질 불량",
           "판넬 쿨러 필터 청소·교체, 냉각팬 점검",
           "판넬 내부 온도 측정, 냉각팬 동작 확인, 공급 전압 측정"),
}
PART_RULES = {
    "TS-04": ("작동유 오염으로 인한 스풀 고착, 코일 과열·공급 전압 이상",
              "솔밸브 세척 또는 교체, 작동유·유압 필터 교체",
              "코일 저항·공급 전압 측정, 수동 조작으로 스풀 동작 확인, 작동유 오염도 확인"),
    "SD-02": ("절삭유 침투에 따른 씰 경화·손상, 클램프 압력 과다",
              "씰 재질 확인 후 교체, 절삭유 차폐 보강",
              "터렛 클램프 압력 측정, 누유 부위 육안 점검, 씰 경화 상태 확인"),
    "HS-04": ("벨트 장력 부족·과다, 풀리 정렬 불량, 벨트 규격 불일치",
              "벨트 장력 조정 후 교체, 풀리 정렬 교정",
              "벨트 장력계 측정, 풀리 정렬(레이저) 확인, 벨트 규격 확인"),
    "TS-07": ("심압대 추력 과다, 공작물 편심·과부하, 회전센터 베어링 윤활 부족",
              "심압대 추력 재설정, 공작물 센터 구멍 상태 점검 후 교체",
              "심압대 추력 측정, 회전센터 회전 저항·진동 측정, 센터 구멍 형상 확인"),
}


def _rule(part_id: str) -> tuple[str, str, str]:
    return PART_RULES.get(part_id) or UNIT_RULES[part_id[:2]]


def _finding(problem, part_id, evidence, severity, extra_cause=None):
    cause, action, check = _rule(part_id)
    if extra_cause:
        cause = f"{extra_cause}, {cause}"
    return {"문제": problem, "추정 원인": f"(추정) {cause}", "권장 조치": action, "확인 방법": check,
            "근거": evidence, "심각도": severity}


def analyze(months: int = 6, equipment: str | None = None, save: bool = False, url: str | None = None,
            out_dir: Path | None = None) -> dict:
    if months < 1:
        raise UserError("--months는 1 이상이어야 합니다.")
    equipment = normalize_equipment(equipment) if equipment else None
    with read_connection(url) as conn:
        data = UsageData(conn)
        prices = {r.part_id: r.unit_price for r in conn.execute(select(schema.parts.c.part_id, schema.parts.c.unit_price))}
    if data.ref_date is None:
        raise UserError("가동로그가 없어 분석 기준일을 정할 수 없습니다.")
    ref = data.ref_date
    start = ref - timedelta(days=round(months * MONTH_DAYS))

    logs = sorted(
        (log for (eq, _), items in data.logs.items() if equipment in (None, eq)
         for log in items if log["log_date"] > start),
        key=lambda log: (log["log_date"], log["id"]),
    )
    breakdowns = [log for log in logs if log["is_breakdown"]]
    part = data.parts

    # ----- 집계 -----
    by_equipment = Counter(log["equipment_id"] for log in breakdowns)
    by_unit = Counter(part[log["part_id"]]["unit"] for log in breakdowns)
    by_assembly = Counter(part[log["part_id"]]["assembly_code"] for log in breakdowns)
    by_part = Counter(log["part_id"] for log in breakdowns)

    monthly = defaultdict(lambda: {"total": 0, "preventive": 0, "breakdown": 0})
    for log in logs:
        m = monthly[log["log_date"].strftime("%Y-%m")]
        m["total"] += 1
        m["breakdown" if log["is_breakdown"] else "preventive"] += 1
    monthly_pm = [{"month": k, **v, "pm_ratio": round(v["preventive"] / v["total"] * 100, 1)}
                  for k, v in sorted(monthly.items())]
    pm_ratio = round((len(logs) - len(breakdowns)) / len(logs) * 100, 1) if logs else None

    cost = sum(prices[log["part_id"]] for log in logs if log["action_type"] == "교체")
    breakdown_cost = sum(prices[log["part_id"]] for log in breakdowns if log["action_type"] == "교체")

    # ----- 반복고장 -----
    groups = defaultdict(list)
    for log in breakdowns:
        groups[(log["equipment_id"], log["part_id"])].append(log["log_date"])
    repeats = []
    for (eq, pid), dates in sorted(groups.items()):
        gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
        if any(g <= REPEAT_WINDOW_DAYS for g in gaps):
            repeats.append({"equipment_id": eq, "part_id": pid, "part_name": part[pid]["part_name"],
                            "count": len(dates), "dates": dates, "min_gap_days": min(gaps)})

    # ----- 조기고장 -----
    earlies = []
    for log in breakdowns:
        if log["action_type"] not in ("교체", "수리"):
            continue
        early = data.early_failure(log["equipment_id"], log["part_id"], log["log_date"], exclude_id=log["id"])
        if early:
            earlies.append({"id": log["id"], "log_date": log["log_date"], "equipment_id": log["equipment_id"],
                            "part_id": log["part_id"], "part_name": part[log["part_id"]]["part_name"],
                            "action_type": log["action_type"], **early})

    # ----- 해석 -----
    findings = []
    for r in repeats:
        findings.append(_finding(
            f"{r['equipment_id']} {r['part_name']}({r['part_id']}) 돌발고장 {r['count']}회 반복 "
            f"(최단 {r['min_gap_days']}일 만에 재발)",
            r["part_id"], {"dates": r["dates"]}, "높음"))
    for e in earlies:
        findings.append(_finding(
            f"{e['equipment_id']} {e['part_name']}({e['part_id']}) 조기고장: 직전 교체 후 "
            f"{fmt_amount(e['usage'], e['basis'])} 사용(교체주기의 {e['usage_pct']}%) 시점에 돌발 {e['action_type']}",
            e["part_id"], {"log_date": e["log_date"], "last_reset": e["last_reset"]}, "높음",
            extra_cause="교체 부품 품질·장착 불량"))
    if breakdowns:
        unit, n = by_unit.most_common(1)[0]
        share = n / len(breakdowns) * 100
        if n >= 3 and share >= 30:
            top_part = max((p for p in by_part if p.startswith(unit)), key=by_part.get)
            findings.append(_finding(
                f"{UNIT_NAMES[unit]}({unit}) 유닛에 돌발고장이 집중됨: {n}건, 전체 돌발의 {share:.0f}%",
                top_part, {"by_unit": dict(by_unit)}, "중간"))
        if not equipment and len(by_equipment) > 1:
            eq, n = by_equipment.most_common(1)[0]
            avg = len(breakdowns) / len(data.installed)
            if n >= 3 and n >= avg * 1.5:
                top_part = max((log["part_id"] for log in breakdowns if log["equipment_id"] == eq), key=by_part.get)
                findings.append(_finding(
                    f"{eq}에 돌발고장이 집중됨: {n}건 (설비 평균 {avg:.1f}건의 {n / avg:.1f}배)",
                    top_part, {"by_equipment": dict(by_equipment)}, "중간"))
    if pm_ratio is not None and pm_ratio < PM_RATIO_TARGET:
        findings.append({
            "문제": f"예방보전 비율 {pm_ratio}%로 목표 {PM_RATIO_TARGET:.0f}%에 못 미침",
            "추정 원인": "(추정) 교체 도래 관리 미흡, 계획 작업 누락, 예비품 부족으로 인한 사후 대응",
            "권장 조치": "교체 도래 점검(due_check)을 주 1회 실행해 PM 계획에 반영, 예비품 확보",
            "확인 방법": "due_check 결과의 초과 건수 추이, 월별 예방보전 비율 추이 확인",
            "근거": {"pm_ratio": pm_ratio}, "심각도": "중간",
        })
    findings.sort(key=lambda f: SEVERITY_ORDER[f["심각도"]])

    result = {
        "reference_date": ref,
        "period": {"from": start + timedelta(days=1), "to": ref, "months": months},
        "filters": {"equipment": equipment},
        "summary": {"total": len(logs), "breakdown": len(breakdowns), "preventive": len(logs) - len(breakdowns),
                    "pm_ratio": pm_ratio, "pm_ratio_target": PM_RATIO_TARGET,
                    "parts_cost": cost, "breakdown_parts_cost": breakdown_cost},
        "breakdowns_by_equipment": dict(by_equipment.most_common()),
        "breakdowns_by_unit": {f"{u} {UNIT_NAMES[u]}": n for u, n in by_unit.most_common()},
        "breakdowns_by_assembly": {f"{a} {ASSEMBLY_NAMES[a]}": n for a, n in by_assembly.most_common()},
        "breakdowns_by_part": [{"part_id": p, "part_name": part[p]["part_name"], "count": n}
                               for p, n in by_part.most_common(10)],
        "monthly_pm_ratio": monthly_pm,
        "repeat_failures": repeats,
        "early_failures": earlies,
        "findings": findings,
        "notes": ["추정 원인은 규칙 기반 추정입니다. 확인 방법으로 반드시 검증하세요.",
                  "부품비는 교체 이력 × 파트 단가(데모용 가정값) 합계이며 인건비·수리비는 포함하지 않습니다."],
    }
    if save:
        result["saved_to"] = str(_save_json(result, ref, out_dir or REPORTS_DIR))
    return result


def _save_json(result: dict, ref, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"analysis_{ref.strftime('%Y%m%d')}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, default=json_default, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="고장 패턴 분석")
    parser.add_argument("--months", type=int, default=6, help="분석 기간(개월, 기본 6)")
    parser.add_argument("--equipment", help="설비 (예: CNC-03, 3호기)")
    parser.add_argument("--save", action="store_true", help="reports/analysis_YYYYMMDD.json 저장")
    parser.add_argument("--format", choices=("json", "table"), default="json")
    args = parser.parse_args()
    result = analyze(args.months, args.equipment, args.save)
    if args.format == "table":
        result = {"rows": result["findings"], "summary": result["summary"], "notes": result["notes"]}
    emit(result, args.format)


if __name__ == "__main__":
    sys.exit(run_cli(main))
