from datetime import date

import pytest

from scripts.common import UserError
from scripts.normalize import (find_date, find_equipment, judge_breakdown, map_action, normalize_equipment, parse)


@pytest.mark.parametrize("text", [
    "3호기", "3번기", "03번", "3번", "CNC3", "cnc-03", "CNC-03", "cnc 3", "CNC_03", "3 호기", "03호기",
    "3번기 척 교체", "어제 3호기에서 조 갈았음",
])
def test_equipment_variants(text):
    assert find_equipment(text) == ["CNC-03"]


@pytest.mark.parametrize("text, expected", [("12호기", "CNC-12"), ("1번기", "CNC-01"), ("cnc10", "CNC-10")])
def test_equipment_range_edges(text, expected):
    assert normalize_equipment(text) == expected


@pytest.mark.parametrize("text", ["13호기", "0번기", "CNC-99"])
def test_equipment_out_of_range(text):
    with pytest.raises(UserError, match="관리 대상이 아닙니다"):
        find_equipment(text)


def test_equipment_plain_number():
    assert normalize_equipment("7") == "CNC-07"


def test_equipment_not_found():
    with pytest.raises(UserError, match="특정할 수 없습니다"):
        normalize_equipment("선반")


@pytest.mark.parametrize("text, expected", [
    ("SD-01 파손", []), ("볼스크류 2개 교체", []),  # 파트ID·수량 숫자는 설비로 보지 않는다
])
def test_numbers_that_are_not_equipment(text, expected):
    assert find_equipment(text) == expected


# prd.md F1 동의어 전부
@pytest.mark.parametrize("text, part_id", [
    ("3호기 죠 교체", "HS-02"),
    ("3호기 조 교체", "HS-02"),
    ("3호기 jaw 교체", "HS-02"),
    ("3호기 공구대 커플링 교체", "SD-01"),
    ("3호기 라이브센터 교체", "TS-07"),
    ("3호기 솔밸브 교체", "TS-04"),
    ("3호기 앱솔 배터리 교체", "EL-01"),
    ("3호기 웨이오일 보충", "LB-01"),
    ("3호기 MC 교체", "EL-07"),
])
def test_synonyms(db_url, text, part_id):
    result = parse(text, db_url)
    assert [c["part_id"] for c in result["parts"]["candidates"]] == [part_id]


def test_bearing_always_br(db_url):
    result = parse("3번기 주축 베어링 소음나서 교체", db_url)
    candidates = result["parts"]["candidates"]
    assert result["parts"]["status"] == "many"
    assert [c["part_id"] for c in candidates] == ["BR-01", "BR-02"]
    assert all(c["unit"] == "BR" for c in candidates)


def test_bearing_without_location_lists_bearings(db_url):
    # 위치 없이 "베어링"만 말하면 이름에 베어링이 들어간 BR 파트가 모두 후보 (LM가이드 블록은 제외)
    candidates = parse("5호기 베어링 교체", db_url)["parts"]["candidates"]
    assert [c["part_id"] for c in candidates] == ["BR-01", "BR-02", "BR-03", "BR-04", "BR-07"]


def test_turret_bearing_is_br_not_sd(db_url):
    candidates = parse("5호기 공구대 베어링 교체", db_url)["parts"]["candidates"]
    assert [c["part_id"] for c in candidates] == ["BR-07"]


def test_partial_keyword_gives_many(db_url):
    result = parse("4호기 필터 교체", db_url)
    assert result["parts"]["status"] == "many"
    assert {"TS-02", "LB-02", "LB-06", "EL-03"} <= {c["part_id"] for c in result["parts"]["candidates"]}


def test_unknown_part_none(db_url):
    result = parse("4호기 뭔가 이상해서 봤음", db_url)
    assert result["parts"]["status"] == "none"
    assert not result["ready"]


@pytest.mark.parametrize("text", [
    # 4단계 검토 C-2: 짧은 별칭이 다른 단어 일부에 걸려 한 파트로 확정되던 문제
    "3호기 볼스크류 조임 불량 수리",
    "5번기 조명 불량 수리",
    "3호기 척 조절 불량 조정",
    "3호기 스핀들 알람 떠서 점검했죠",
    "3호기 머시닝센터 교체",
    "3호기 UPS 교체",
])
def test_short_alias_not_confirmed_from_part_of_word(db_url, text):
    candidates = [c["part_id"] for c in parse(text, db_url)["parts"]["candidates"]]
    assert candidates not in (["HS-02"], ["TS-07"], ["TS-05"]), candidates


@pytest.mark.parametrize("text, part_id", [
    ("3호기 조 교체", "HS-02"), ("3호기 죠를 교체", "HS-02"), ("3호기 척 교체", "HS-01"),
    ("3호기 척을 교체", "HS-01"), ("3호기 벨트가 끊어짐", "HS-04"), ("3호기 팬 교체", "EL-04"),
])
def test_short_alias_as_whole_word(db_url, text, part_id):
    assert [c["part_id"] for c in parse(text, db_url)["parts"]["candidates"]] == [part_id]


def test_adjust_word_not_mistaken_for_jaw(db_url):
    candidates = parse("4호기 터렛 인덱싱 모터 조정", db_url)["parts"]["candidates"]
    assert [c["part_id"] for c in candidates] == ["SD-03"]


@pytest.mark.parametrize("text, action", [
    ("벨트 갈았어", "교체"), ("척 교환", "교체"), ("펌프 고쳤음", "수리"), ("조 맞췄다", "조정"),
    ("필터 닦았음", "청소"), ("소음 봤음", "점검"), ("습동유 채웠다", "보충"), ("점검 후 교체", "교체"),
    ("오늘 뭐 했지", None),
])
def test_action_mapping(text, action):
    assert map_action(text) == action


@pytest.mark.parametrize("text, expected", [
    ("알람 떠서 교체", True), ("설비 정지", True), ("커플링 파손", True), ("씰 누유", True), ("가공 불량", True),
    ("베어링 소음", True), ("주기 도래 교체", False), ("PM 작업", False), ("예방 교체", False),
    ("정기 점검", False), ("정기 점검 중 누유 발견", True), ("그냥 교체", None),
])
def test_breakdown_judgement(text, expected):
    assert judge_breakdown(text)[0] is expected


@pytest.mark.parametrize("text, expected", [
    ("2026-09-20 교체", date(2026, 9, 20)), ("9월 20일 교체", date(2026, 9, 20)), ("9/20 교체", date(2026, 9, 20)),
    ("어제 교체", date(2026, 9, 28)), ("오늘 교체", date(2026, 9, 29)), ("그제 교체", date(2026, 9, 27)),
    ("12월 1일 교체", date(2025, 12, 1)),  # 미래 날짜면 작년으로
    ("교체", None),
])
def test_find_date(text, expected):
    assert find_date(text, today=date(2026, 9, 29)) == expected


def test_invalid_date():
    with pytest.raises(UserError, match="날짜"):
        find_date("13월 40일 교체", today=date(2026, 9, 29))


def test_parse_ready_sentence(db_url):
    result = parse("3번기 주축 전면 베어링 소음나서 교체", db_url, today=date(2026, 9, 29))
    assert result["equipment"] == "CNC-03"
    assert [c["part_id"] for c in result["parts"]["candidates"]] == ["BR-01"]
    assert result["action"] == "교체" and result["breakdown"] is True
    assert result["date_defaulted"] and result["ready"]


def test_parse_asks_when_missing(db_url):
    result = parse("벨트 갈았어", db_url)
    assert result["equipment"] is None
    assert any("설비" in q for q in result["questions"])
    assert any("돌발" in q for q in result["questions"])
    assert not result["ready"]


def test_parse_out_of_range_question(db_url):
    result = parse("13호기 척 교체", db_url)
    assert any("13호기는 관리 대상이 아닙니다" in q for q in result["questions"])
