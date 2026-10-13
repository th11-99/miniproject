"""Streamlit 화면 기본 동작 (streamlit.testing.v1.AppTest)."""

import pytest
from streamlit.testing.v1 import AppTest

from scripts.common import ROOT, fetch_all, read_connection

PAGES = ["dashboard", "equipment_detail", "register", "due", "analysis", "history"]


def _count(url):
    with read_connection(url) as conn:
        return fetch_all(conn, "SELECT COUNT(*) AS n FROM repair_logs")[0]["n"]


@pytest.fixture
def app(monkeypatch):
    def start(url, page="dashboard"):
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.chdir(ROOT)  # st.Page 경로는 실행 위치 기준
        at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60).run()
        if page != "dashboard":
            at.switch_page(f"app_pages/{page}.py").run()
        return at
    return start


def _no_errors(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_opens(app, db_url, page):
    _no_errors(app(db_url, page))


def test_dashboard_metrics_and_grid(app, db_url):
    at = app(db_url)
    labels = [m.label for m in at.metric]
    assert labels[:2] == ["교체 초과", "30일 내 도래"]
    assert any(label.startswith("이번 달 돌발고장") for label in labels)
    assert any(label.startswith("예방보전 비율") for label in labels)
    assert len([b for b in at.button if b.key and b.key.startswith("eq_btn_")]) == 12


def test_dashboard_to_detail(app, db_url):
    at = app(db_url)
    at.button(key="eq_btn_CNC-07").click().run()
    _no_errors(at)
    assert at.title[0].value == "설비 상세"
    assert at.selectbox(key="detail_equipment_select").value == "CNC-07"
    assert len(at.tabs) == 10  # 구조부 10개


def test_detail_specs(app, db_url):
    at = app(db_url, "equipment_detail")
    labels = {m.label for m in at.metric}
    assert {"최고 회전수", "퀼 테이퍼", "습동면 방식", "컨트롤러"} <= labels


def test_due_filters_and_download(app, db_url):
    at = app(db_url, "due")
    assert any("데모용 가정값" in i.value for i in at.info)
    at.selectbox(key="due_unit").set_value("TS").run()
    at.segmented_control(key="due_days").set_value(90).run()
    _no_errors(at)
    assert at.get("download_button")


def test_analysis_findings_cards(app, db_url):
    at = app(db_url, "analysis")
    text = " ".join(m.value for m in at.markdown)
    assert "**추정 원인**" in text and "**확인 방법**" in text
    at.segmented_control(key="ana_months").set_value(12).run()
    at.selectbox(key="ana_equipment").set_value("CNC-07").run()
    _no_errors(at)


def test_history_filters(app, db_url):
    at = app(db_url, "history")
    at.selectbox(key="hist_equipment").set_value("CNC-02").run()
    at.segmented_control(key="hist_breakdown").set_value("돌발").run()
    _no_errors(at)
    assert at.dataframe


# ---------- 이력 등록: 미리보기 → 확인 → 등록 ----------


def test_detail_to_register_prefills_form(app, db_url):
    at = app(db_url, "equipment_detail")
    assert len([b for b in at.button if b.key and b.key.startswith("detail_reg_btn_")]) >= 8  # 파트가 있는 구조부마다
    at.selectbox(key="detail_reg_part_HDS").set_value("HS-02").run()
    at.button(key="detail_reg_btn_HDS").click().run()
    _no_errors(at)
    assert at.title[0].value == "이력 등록"
    assert at.selectbox(key="reg_equipment").value == "CNC-01"
    assert at.selectbox(key="reg_part").value.startswith("HS-02")
    assert at.segmented_control(key="reg_action").value == "교체"
    assert at.segmented_control(key="reg_breakdown").value == "예방"
    assert any("설비 상세에서 넘어왔습니다" in i.value for i in at.info)
    assert not at.button(key="preview_btn").disabled


def test_detail_to_register_periodic_action(app, db_url):
    """습동유(LB-01)는 보충이 주기 작업이므로 조치 기본값이 보충."""
    at = app(db_url, "equipment_detail")
    at.selectbox(key="detail_reg_part_BED").set_value("LB-01").run()
    at.button(key="detail_reg_btn_BED").click().run()
    assert at.segmented_control(key="reg_action").value == "보충"

def _parse(at, text):
    at.text_input(key="nl_input").input(text).run()
    at.button(key="parse_btn").click().run()
    return at


def test_register_parse_fills_form(app, db_url):
    at = _parse(app(db_url, "register"), "3번기 주축 베어링 소음나서 교체")
    assert at.selectbox(key="reg_equipment").value == "CNC-03"
    assert at.radio(key="reg_part").options == ["BR-01 스핀들 전면 베어링", "BR-02 스핀들 후면 베어링"]
    assert at.segmented_control(key="reg_action").value == "교체"
    assert at.segmented_control(key="reg_breakdown").value == "돌발"
    assert at.button(key="register_btn").disabled  # 미리보기 전


def test_register_needs_missing_fields(app, db_url):
    at = _parse(app(db_url, "register"), "벨트 갈았어")
    assert at.button(key="preview_btn").disabled  # 설비·구분이 비어 있음
    assert any("어느 설비" in w.value for w in at.warning)


def test_register_part_not_found_unit_select(app, db_url):
    at = _parse(app(db_url, "register"), "4호기 뭔가 봤음")
    assert any("파트를 찾지 못했습니다" in w.value for w in at.warning)
    at.selectbox(key="reg_unit").set_value("EL").run()
    assert "EL-01 APC 배터리" in at.selectbox(key="reg_part").options


def test_preview_does_not_write_and_shows_info(app, writable_db_url):
    url = writable_db_url
    before = _count(url)
    at = _parse(app(url, "register"), "5호기 스핀들 벨트 끊어져서 교체")
    at.button(key="preview_btn").click().run()
    assert not at.exception
    assert _count(url) == before
    assert not at.button(key="register_btn").disabled
    # 조기고장·반복고장은 빨간 경고(st.error)로 강조
    errors = [e.value for e in at.error]
    assert any("조기고장" in e for e in errors) and any("반복고장" in e for e in errors)


def test_change_after_preview_invalidates(app, writable_db_url):
    at = _parse(app(writable_db_url, "register"), "5호기 스핀들 벨트 끊어져서 교체")
    at.button(key="preview_btn").click().run()
    at.segmented_control(key="reg_action").set_value("수리").run()
    assert at.button(key="register_btn").disabled
    assert any("입력이 바뀌었습니다" in w.value for w in at.warning)


def test_register_confirm_writes_once(app, writable_db_url):
    url = writable_db_url
    before = _count(url)
    at = _parse(app(url, "register"), "5호기 스핀들 벨트 끊어져서 교체")
    at.button(key="preview_btn").click().run()
    at.button(key="register_btn").click().run()
    at.button(key="confirm_register_btn").click().run()
    assert not at.exception
    assert not any("등록하지 못했습니다" in e.value for e in at.error)
    assert _count(url) == before + 1
    assert any("등록 완료" in s.value for s in at.success)
    # 같은 미리보기로는 다시 등록할 수 없다 (연타·재실행 방지)
    assert at.button(key="register_btn").disabled
    at.run()
    assert _count(url) == before + 1


def test_register_cancel_writes_nothing(app, writable_db_url):
    url = writable_db_url
    before = _count(url)
    at = _parse(app(url, "register"), "5호기 스핀들 벨트 끊어져서 교체")
    at.button(key="preview_btn").click().run()
    at.button(key="register_btn").click().run()
    at.button(key="cancel_register_btn").click().run()
    assert _count(url) == before
    assert not at.button(key="register_btn").disabled  # 미리보기는 유지


def test_missing_db_shows_guidance(app, tmp_path):
    at = app(f"sqlite:///{(tmp_path / 'none.db').as_posix()}")
    assert not at.exception
    assert any("init_db" in e.value for e in at.error)
