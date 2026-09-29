"""현장 용어 해석: 자연어 한 문장 → 설비·파트 후보·조치 유형·돌발 여부·날짜.

  python scripts/normalize.py "3번기 주축 베어링 소음나서 교체"

해석이 불완전하면 추측하지 않고 questions에 되물을 내용을 담는다.
"""

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from scripts import schema  # noqa: E402
from scripts.common import UserError, emit, read_connection, run_cli  # noqa: E402

EQUIPMENT_COUNT = 12

# ---------- 설비 ----------

_EQ_PATTERNS = [
    re.compile(r"(?i)cnc\s*[-_]?\s*(\d{1,3})(?!\d)"),
    re.compile(r"(?<!\d)(\d{1,3})\s*(?:호기|번기|번\s*설비|번|호)"),
]


def _equipment_id(number: int) -> str:
    if not 1 <= number <= EQUIPMENT_COUNT:
        raise UserError(f"{number}호기는 관리 대상이 아닙니다 (CNC-01 ~ CNC-{EQUIPMENT_COUNT:02d}).")
    return f"CNC-{number:02d}"


def find_equipment(text: str) -> list[str]:
    """문장에서 설비를 찾아 CNC-NN 목록으로 돌려준다 (중복 제거, 등장 순). 범위 밖이면 UserError."""
    found: list[tuple[int, int]] = []
    for pattern in _EQ_PATTERNS:
        found += [(m.start(), int(m.group(1))) for m in pattern.finditer(text)]
    ids = []
    for _, number in sorted(found):
        eq = _equipment_id(number)
        if eq not in ids:
            ids.append(eq)
    return ids


def normalize_equipment(value: str) -> str:
    """단일 설비 표현("3호기", "cnc-03", "3")을 CNC-03으로. 못 찾거나 여러 개면 UserError."""
    value = value.strip()
    if value.isdigit():
        return _equipment_id(int(value))
    ids = find_equipment(value)
    if len(ids) != 1:
        raise UserError(f"설비를 특정할 수 없습니다: {value} (예: 3호기, CNC-03)")
    return ids[0]


def _remove_equipment(text: str) -> str:
    for pattern in _EQ_PATTERNS:
        text = pattern.sub(" ", text)
    return text


# ---------- 파트 ----------

# 현장 동의어 → 표준어 (prd.md F1)
SYNONYMS = [
    (r"공구대", "터렛"),
    (r"라이브\s*센터", "회전센터"),
    (r"죠|jaw", "조"),
    (r"솔\s*밸브", "솔레노이드 밸브"),
    (r"(?:앱솔|엡솔|앱솔루트)\s*배터리", "APC 배터리"),
    (r"웨이\s*오일|way\s*oil", "습동유"),
    (r"(?<![a-z])mc(?![a-z])", "마그네트 접촉기"),
]

# 파트 이름으로 오인하기 쉬운 일반 단어 (예: '조정'의 '조'가 척 조로 잡히는 것 방지)
_STOPWORDS = r"조정|조절|조임|조명|조치|조립|조금|조작|구조|확인|이상\s*없"
_PARTICLE = re.compile(r"(을|를|이|가|은|는|의|에|도|만|랑|하고|쪽)$")


def canonical(text: str) -> str:
    text = text.lower()
    for pattern, repl in SYNONYMS:
        text = re.sub(pattern, repl.lower(), text)
    return text


def compact(text: str) -> str:
    return re.sub(r"[\s\-_/·,.()]+", "", text.lower())


def _part_names(part: dict) -> list[str]:
    return [n for n in [part["part_name"], *part["aliases"].split(",")] if n.strip()]


def find_parts(text: str, parts: list[dict]) -> dict:
    """문장에 들어 있는 파트 별칭을 찾아 후보를 돌려준다.

    가장 길게 일치한 별칭의 파트만 후보로 남긴다("주축 전면 베어링" → BR-01).
    일치하는 별칭이 없으면 문장 속 단어가 들어 있는 파트를 후보로 한다("필터" → 필터류 전부).
    "베어링"이 있으면 항상 BR 유닛만 후보로 한다.
    """
    cleaned = re.sub(_STOPWORDS, " ", _remove_equipment(canonical(text)))
    for _, words in ACTIONS:
        cleaned = re.sub("|".join(words), " ", cleaned)
    target = compact(cleaned)
    words = {_PARTICLE.sub("", compact(w)) for w in cleaned.split()}  # 조사를 뗀 어절
    bearing_only = "베어링" in target
    pool = [p for p in parts if p["unit"] == "BR"] if bearing_only else parts

    scores: dict[str, tuple[int, str]] = {}
    for p in pool:
        for name in _part_names(p):
            key = compact(canonical(name))
            # 2글자 이하 별칭('조', '척', '센터', 'PS')은 어절 전체가 같을 때만 인정한다.
            # 부분 일치를 허용하면 '조임'·'조명'·'했죠'(→했조)·'머시닝센터'·'UPS'가 해당 파트로 확정된다.
            short_single = len(key) <= 2 and " " not in name.strip()
            matched = key in words if short_single else key in target
            if key and matched and len(key) > scores.get(p["part_id"], (0, ""))[0]:
                scores[p["part_id"]] = (len(key), name.strip())
    if scores:
        best = max(s for s, _ in scores.values())
        chosen = {pid: name for pid, (s, name) in scores.items() if s == best}
    else:  # 단어가 별칭의 일부인 경우 ("볼스크류" → X/Z 볼스크류)
        tokens = [compact(t) for t in re.split(r"\s+", cleaned) if len(compact(t)) >= 2]
        tokens = [_PARTICLE.sub("", t) for t in tokens]
        chosen = {}
        for p in pool:
            for name in _part_names(p):
                key = compact(canonical(name))
                if any(len(t) >= 2 and t in key for t in tokens):
                    chosen[p["part_id"]] = name.strip()
                    break
        if not chosen and bearing_only:
            chosen = {p["part_id"]: "베어링" for p in pool}

    candidates = [
        {"part_id": p["part_id"], "part_name": p["part_name"], "unit": p["unit"],
         "assembly_code": p["assembly_code"], "matched": chosen[p["part_id"]]}
        for p in parts if p["part_id"] in chosen
    ]
    status = "none" if not candidates else "one" if len(candidates) == 1 else "many"
    return {"status": status, "candidates": candidates}


def load_parts(conn) -> list[dict]:
    p = schema.parts.c
    return [dict(r._mapping) for r in conn.execute(
        select(p.part_id, p.part_name, p.aliases, p.unit, p.assembly_code).order_by(p.part_id))]


# ---------- 조치 유형·돌발 ----------

# 우선순위 순서 ("점검 후 교체" → 교체)
ACTIONS = [
    ("교체", ["교체", "교환", "갈았", "갈아", "갈음", "바꿨", "바꿔", "바꾸", "체인지"]),
    ("수리", ["수리", "고쳤", "고침", "고치", "수선", "보수"]),
    ("조정", ["조정", "맞췄", "맞춤", "맞추", "세팅", "셋팅"]),
    ("보충", ["보충", "채웠", "채움", "채우", "주입", "급유", "보급"]),
    ("청소", ["청소", "닦았", "닦음", "닦아", "세척"]),
    ("점검", ["점검", "봤", "보았", "확인", "체크", "검사"]),
]
BREAKDOWN_WORDS = ["알람", "정지", "멈춤", "멈췄", "파손", "깨짐", "깨졌", "부러", "끊어", "끊김", "누유", "새서",
                   "새는", "샌다", "불량", "고장", "소음", "진동", "에러", "발열", "과열", "떨림", "튐"]
PREVENTIVE_WORDS = ["주기", "도래", "pm", "예방", "정기", "계획"]


def map_action(text: str) -> str | None:
    t = text.lower()
    for action, words in ACTIONS:
        if any(w in t for w in words):
            return action
    return None


def judge_breakdown(text: str) -> tuple[bool | None, str | None]:
    """(돌발 여부, 근거 단어). 돌발 단어가 예방 단어보다 우선. 둘 다 없으면 (None, None)."""
    t = text.lower()
    for w in BREAKDOWN_WORDS:
        if w in t:
            return True, w
    for w in PREVENTIVE_WORDS:
        if w in t:
            return False, w.upper() if w == "pm" else w
    return None, None


# ---------- 날짜 ----------

def find_date(text: str, today: date | None = None) -> date | None:
    today = today or date.today()
    try:
        if m := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text):
            return date(int(m[1]), int(m[2]), int(m[3]))
        m = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", text) or re.search(r"(?<![\d.])(\d{1,2})/(\d{1,2})(?![\d/])", text)
        if m:
            d = date(today.year, int(m[1]), int(m[2]))
            return d if d <= today else date(today.year - 1, d.month, d.day)
    except ValueError as exc:
        raise UserError(f"날짜를 이해할 수 없습니다: {m[0]}") from exc
    for words, delta in ((("그제", "그저께"), 2), (("어제", "전일"), 1), (("오늘", "금일"), 0)):
        if any(w in text for w in words):
            return today - timedelta(days=delta)
    return None


# ---------- 전체 해석 ----------

def parse(text: str, url: str | None = None, today: date | None = None) -> dict:
    questions = []
    equipment_error = None
    try:
        eq_ids = find_equipment(text)
    except UserError as exc:
        eq_ids, equipment_error = [], str(exc)
    if equipment_error:
        questions.append(equipment_error)
    elif not eq_ids:
        questions.append("어느 설비인가요? (예: 3호기, CNC-03)")
    elif len(eq_ids) > 1:
        questions.append(f"설비가 여러 개입니다: {', '.join(eq_ids)} 중 하나를 골라 주세요.")

    with read_connection(url) as conn:
        parts = find_parts(text, load_parts(conn))
    if parts["status"] == "none":
        questions.append("어떤 파트인가요? 유닛(주축대·심압대·새들·베어링류·윤활라인·전기판넬)이나 파트명을 알려 주세요.")
    elif parts["status"] == "many":
        names = ", ".join(f"{c['part_id']} {c['part_name']}" for c in parts["candidates"])
        questions.append(f"파트 후보가 여러 개입니다: {names} 중 어느 것인가요?")

    action = map_action(text)
    if action is None:
        questions.append("조치 유형을 알려 주세요: 교체 / 수리 / 조정 / 청소 / 점검 / 보충")
    breakdown, reason = judge_breakdown(text)
    if breakdown is None:
        questions.append("예정에 없던 고장 대응(돌발)인가요, 계획된 예방 작업인가요?")
    log_date = find_date(text, today)

    return {
        "input": text,
        "equipment": eq_ids[0] if len(eq_ids) == 1 else None,
        "equipment_candidates": eq_ids,
        "parts": parts,
        "action": action,
        "breakdown": breakdown,
        "breakdown_reason": reason,
        "date": log_date,
        "date_defaulted": log_date is None,  # None이면 등록 시 오늘
        "questions": questions,
        "ready": not questions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="현장 표현 해석 (설비·파트 후보·조치·돌발·날짜)")
    parser.add_argument("text", help='예: "3번기 주축 베어링 소음나서 교체"')
    parser.add_argument("--format", choices=("json", "table"), default="json")
    args = parser.parse_args()
    result = parse(args.text)
    if args.format == "table":
        result = {**result, "rows": result["parts"]["candidates"]}
    emit(result, args.format)


if __name__ == "__main__":
    sys.exit(run_cli(main))
