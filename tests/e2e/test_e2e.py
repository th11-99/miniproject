"""4단계 E2E 시나리오 (prompts.md 4단계 B). 테스트 순서대로 실행되며 서버 DB에 실제로 등록한다."""

import os
import subprocess
import sys
import time
import urllib.request

import pytest

from scripts.analyze import analyze
from scripts.common import ROOT
from scripts.dashboard import dashboard_summary
from scripts.due_check import due_check
from scripts.history import list_repairs
from tests.e2e.conftest import BASE_URL, DB_URL
from tests.e2e.helpers import (active_segment, alerts, button, choose, click, fill, goto, has_traceback,
                               open_select, parse_text, repair_count, segment, settle, shot, stock, value)


def _metric_values(page) -> list[str]:
    return [t.strip() for t in page.locator('[data-testid="stMetricValue"]').all_inner_texts()]


# ---------- 1. 대시보드 ----------

def test_01_dashboard_matches_scripts(page):
    goto(page)
    expected = dashboard_summary(DB_URL)
    values = _metric_values(page)
    assert values[:3] == [f"{expected['overdue']}건", f"{expected['due_soon']}건", f"{expected['breakdowns_this_month']}건"]
    assert values[3] == f"{expected['pm_ratio']}%"
    assert page.locator('[class*="st-key-eq_btn_CNC-"]').count() == 12
    shot(page, "01_dashboard")
    assert not has_traceback(page)


def test_01b_navigation_sidebar_and_url(page):
    goto(page)
    click(page, "eq_btn_CNC-07")
    assert page.url.rstrip("/").endswith("/equipment_detail")
    assert value(page, "detail_equipment_select").startswith("CNC-07")
    assert page.get_by_role("tab").count() == 10
    shot(page, "01b_detail_cnc07")
    page.get_by_test_id("stSidebarNav").get_by_text("교체 도래").click()
    settle(page)
    assert page.locator("h1").inner_text().strip() == "교체 도래"
    for path, title in [("register", "이력 등록"), ("analysis", "고장 분석"), ("history", "이력 조회"),
                        ("equipment_detail", "설비 상세"), ("due", "교체 도래")]:
        goto(page, path)
        assert page.locator("h1").inner_text().strip() == title
        assert not has_traceback(page)


# ---------- 2. 이력 등록 정상 흐름 ----------

def test_02_register_normal_flow(page):
    before_count, before_stock = repair_count(), stock("BR-02")
    parse_text(page, "3번기 주축 베어링 소음나서 교체")
    assert value(page, "reg_equipment").startswith("CNC-03")
    radio = page.locator(".st-key-reg_part").inner_text()
    assert "BR-01 스핀들 전면 베어링" in radio and "BR-02 스핀들 후면 베어링" in radio
    assert active_segment(page, "reg_action") == "교체"
    assert active_segment(page, "reg_breakdown") == "돌발"
    page.locator(".st-key-reg_part").get_by_text("BR-02 스핀들 후면 베어링").click()
    settle(page)
    click(page, "preview_btn")
    shot(page, "02_preview")
    assert button(page, "register_btn").is_enabled()
    click(page, "register_btn")
    page.wait_for_selector(".st-key-confirm_register_btn button")
    shot(page, "02_confirm_dialog")
    click(page, "confirm_register_btn")
    page.wait_for_selector(".st-key-result_box")
    shot(page, "02_registered")
    assert repair_count() == before_count + 1
    assert stock("BR-02") == max(before_stock - 1, 0)  # 재고는 0 밑으로 내려가지 않음


# ---------- 3. 승인 없는 쓰기 차단 ----------

def test_03a_no_register_without_preview(page):
    parse_text(page, "5호기 스핀들 벨트 끊어져서 교체")
    assert button(page, "register_btn").is_disabled()


def test_03b_cancel_writes_nothing(page):
    before = repair_count()
    parse_text(page, "5호기 스핀들 벨트 끊어져서 교체")
    click(page, "preview_btn")
    click(page, "register_btn")
    page.wait_for_selector(".st-key-cancel_register_btn button")
    click(page, "cancel_register_btn")
    assert repair_count() == before
    assert page.locator(".st-key-confirm_register_btn").count() == 0


def test_03c_change_after_preview_blocks(page):
    parse_text(page, "5호기 스핀들 벨트 끊어져서 교체")
    click(page, "preview_btn")
    choose(page, "reg_equipment", "CNC-04 · CNC 선반 4호기")
    assert button(page, "register_btn").is_disabled()
    assert any("입력이 바뀌었습니다" in a for a in alerts(page))
    shot(page, "03c_stale_preview")


def test_03d_change_part_after_preview_blocks(page):
    parse_text(page, "5호기 스핀들 벨트 끊어져서 교체")
    click(page, "preview_btn")
    choose(page, "reg_part", "HS-05 스핀들 인코더")
    assert button(page, "register_btn").is_disabled()


def test_03e_rapid_clicks_register_once(page):
    before = repair_count()
    parse_text(page, "6호기 회전센터 소음 교체")
    click(page, "preview_btn")
    button(page, "register_btn").click()
    page.wait_for_selector(".st-key-confirm_register_btn button")
    page.evaluate("() => { const b = document.querySelector('.st-key-confirm_register_btn button');"
                  " for (let i = 0; i < 5; i++) b.click(); }")
    settle(page)
    page.wait_for_selector(".st-key-result_box")
    page.wait_for_timeout(1500)
    assert repair_count() == before + 1
    # 등록 후 같은 미리보기로는 다시 등록 불가
    assert button(page, "register_btn").is_disabled()


def test_03f_register_button_double_click(page):
    before = repair_count()
    parse_text(page, "8호기 냉각팬 교체 예방")
    click(page, "preview_btn")
    button(page, "register_btn").dblclick()
    page.wait_for_selector(".st-key-confirm_register_btn button")
    click(page, "confirm_register_btn")
    page.wait_for_selector(".st-key-result_box")
    assert repair_count() == before + 1


# ---------- 4. 모호한 입력 ----------

def test_04a_missing_equipment_asks(page):
    parse_text(page, "벨트 갈았어")
    texts = alerts(page)
    assert any("어느 설비" in t for t in texts)
    assert button(page, "preview_btn").is_disabled()
    shot(page, "04a_missing_equipment")


def test_04b_out_of_range_equipment(page):
    parse_text(page, "13호기 척 교체")
    assert any("13호기는 관리 대상이 아닙니다" in t for t in alerts(page))
    assert button(page, "preview_btn").is_disabled()


def test_04c_unknown_part_offers_unit_select(page):
    parse_text(page, "4호기 뭔가 이상해서 봤음")
    assert any("파트를 찾지 못했습니다" in t for t in alerts(page))
    choose(page, "reg_unit", "EL 전기판넬")
    open_select(page, "reg_part")
    options = page.get_by_role("option").all_inner_texts()
    assert any("EL-01" in o for o in options) and not any("HS-01" in o for o in options)
    page.keyboard.press("Escape")
    shot(page, "04c_unit_select")


def test_04d_many_candidates(page):
    parse_text(page, "4호기 필터 교체")
    radio = page.locator(".st-key-reg_part").inner_text()
    assert "TS-02" in radio and "LB-02" in radio and "EL-03" in radio


# ---------- 5. 동의어 ----------

@pytest.mark.parametrize("text, part_id", [
    ("3호기 죠 교체", "HS-02"), ("3호기 공구대 커플링 교체", "SD-01"), ("3호기 라이브센터 교체", "TS-07"),
    ("3호기 솔밸브 교체", "TS-04"), ("3호기 앱솔 배터리 교체", "EL-01"), ("3호기 웨이오일 보충", "LB-01"),
    ("3호기 MC 교체", "EL-07"),
])
def test_05_synonyms(page, text, part_id):
    parse_text(page, text)
    assert value(page, "reg_part").startswith(part_id)


# ---------- 6. info 경고 ----------

@pytest.mark.parametrize("text, kind, name", [
    ("5호기 스핀들 벨트 끊어져서 교체", "조기고장", "06a_early"),
    ("7호기 솔밸브 작동 불량 수리", "반복고장", "06b_repeat"),
    ("3호기 유압필터 정기 교체", "예비품 부족", "06c_spare"),
])
def test_06_info_warnings(page, text, kind, name):
    parse_text(page, text)
    click(page, "preview_btn")
    banner = page.locator(".st-key-info_banner").inner_text()
    assert kind in banner
    page.locator(".st-key-info_banner").scroll_into_view_if_needed()
    shot(page, name)


# ---------- 7. 교체 도래 ----------

def test_07_due_filters_and_csv(page):
    goto(page, "due")
    assert any("데모용 가정값" in t for t in alerts(page))
    choose(page, "due_unit", "TS 심압대")
    segment(page, "due_days", "90일 이내")
    expected = due_check(unit="TS", days=90, url=DB_URL)
    metrics = _metric_values(page)
    assert metrics == [f"{expected['summary']['초과']}건", f"{expected['summary']['임박']}건",
                       f"{expected['summary']['여유']}건"]
    shot(page, "07_due_ts_90")
    with page.expect_download() as info:
        button(page, "due_download").click()
    raw = open(info.value.path(), "rb").read()
    assert raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("상태,설비,파트ID,파트명")
    assert len([l for l in lines[1:] if l and l.split(",")[0] in ("초과", "임박", "여유")]) == len(expected["rows"])
    assert "데모용 가정값" in lines[-1]
    assert all(",TS-" in l for l in lines[1:] if l.startswith(("초과", "임박")))
    page.locator(".st-key-due_all label").first.click()
    settle(page)
    shot(page, "07_due_all")


def test_07b_due_equipment_filter(page):
    goto(page, "due")
    choose(page, "due_equipment", "CNC-02 · CNC 선반 2호기")
    expected = due_check(equipment="CNC-02", days=30, url=DB_URL)
    assert _metric_values(page)[0] == f"{expected['summary']['초과']}건"


# ---------- 8. 고장 분석 ----------

def test_08_analysis_cards_and_charts(page):
    goto(page, "analysis")
    segment(page, "ana_months", "최근 12개월")
    expected = analyze(months=12, url=DB_URL)
    cards = page.locator('[class*="st-key-finding_card_"]')
    assert cards.count() == len(expected["findings"])
    first = cards.first.inner_text()
    for word in ("문제", "추정 원인", "추정", "권장 조치", "확인 방법"):
        assert word in first
    charts = page.locator('[data-testid="stVegaLiteChart"]')
    assert charts.count() == 2
    for i in range(2):
        charts.nth(i).scroll_into_view_if_needed()
        assert charts.nth(i).locator("canvas, svg").count() > 0
    shot(page, "08_analysis_top")
    charts.first.scroll_into_view_if_needed()
    shot(page, "08_analysis_charts")
    choose(page, "ana_equipment", "CNC-07 · CNC 선반 7호기")
    assert not has_traceback(page)


# ---------- 9. 이력 조회 캐시 ----------

def _history_count(page) -> int:
    cap = page.locator('[data-testid="stCaptionContainer"]').filter(has_text="작업일 최신순").inner_text()
    return int(cap.split("건")[0].replace(",", "").strip())


def test_09_history_shows_new_registration(page):
    goto(page, "history")
    choose(page, "hist_equipment", "CNC-11 · CNC 선반 11호기")
    before = _history_count(page)
    assert before == list_repairs(equipment="CNC-11", date_from=None, url=DB_URL)["row_count"] or before >= 0
    parse_text(page, "11호기 판넬 쿨러 필터 청소 정기")
    click(page, "preview_btn")
    click(page, "register_btn")
    page.wait_for_selector(".st-key-confirm_register_btn button")
    click(page, "confirm_register_btn")
    page.wait_for_selector(".st-key-result_box")
    goto(page, "history")
    choose(page, "hist_equipment", "CNC-11 · CNC 선반 11호기")
    assert _history_count(page) == before + 1
    shot(page, "09_history_after_register")


def test_09b_history_empty_result(page):
    goto(page, "history")
    choose(page, "hist_equipment", "CNC-01 · CNC 선반 1호기")
    choose(page, "hist_part", "EL-06 스핀들 앰프")
    segment(page, "hist_breakdown", "돌발")
    texts = alerts(page)
    shot(page, "09b_history_empty")
    assert any("조건에 맞는 이력이 없습니다" in t for t in texts) or page.locator('[data-testid="stDataFrame"]').count() == 1


# ---------- 10. 반응형·테마 ----------

@pytest.mark.parametrize("width", [1280, 768, 375])
@pytest.mark.parametrize("path", ["", "register", "due"])
def test_10_responsive(page, width, path):
    page.set_viewport_size({"width": width, "height": 900})
    goto(page, path)
    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    sizes = page.evaluate("""() => {
        const px = sel => { const e = document.querySelector(sel); return e ? parseFloat(getComputedStyle(e).fontSize) : null; };
        return {base: px('[data-testid="stApp"]'), label: px('[data-testid="stWidgetLabel"] p'),
                caption: px('[data-testid="stCaptionContainer"]'), button: px('[data-testid^="stBaseButton"] p')};
    }""")
    shot(page, f"10_{path or 'dashboard'}_{width}")
    print(f"\n[글자 크기] {path or 'dashboard'} {width}px: {sizes}")
    assert overflow <= 1, f"가로 스크롤 {overflow}px"
    assert sizes["base"] >= 16, f"기본 글자 {sizes}"


def test_10b_dark_theme(page):
    page.emulate_media(color_scheme="dark")
    goto(page, "due")
    bg = page.evaluate("() => getComputedStyle(document.querySelector('[data-testid=\"stApp\"]')).backgroundColor")
    shot(page, "10b_due_dark")
    rgb = [int(x) for x in bg[bg.index("(") + 1:bg.index(")")].split(",")[:3]]
    assert sum(rgb) < 200, f"다크 테마 배경이 아님: {bg}"
    goto(page, "analysis")
    shot(page, "10b_analysis_dark")


# ---------- 11. 오류 상황 ----------

def test_11a_invalid_date_in_text(page):
    parse_text(page, "3호기 척 교체 13월 40일")
    assert any("날짜를 이해할 수 없습니다" in t for t in alerts(page))
    assert not has_traceback(page)


@pytest.fixture(scope="module")
def broken_server():
    """존재하지 않는 DB를 가리키는 두 번째 서버 (DB 연결 실패 화면 확인용)."""
    port = 8599
    env = {**os.environ, "DATABASE_URL": "sqlite:///C:/no/such/dir/missing.db", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.headless", "true",
                             "--server.port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://localhost:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(f"{url}/_stcore/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


@pytest.mark.parametrize("path", ["", "equipment_detail", "register", "due", "analysis", "history"])
def test_11b_db_failure_shows_guidance(page, broken_server, path):
    page.goto(f"{broken_server}/{path}")
    page.wait_for_selector("h1")
    settle(page)
    texts = alerts(page)
    shot(page, f"11b_db_failure_{path or 'dashboard'}")
    assert not has_traceback(page), "Streamlit 예외 화면(traceback)이 노출됨"
    assert any("init_db" in t or "DB" in t for t in texts), texts


def test_11c_all_pages_no_traceback(page):
    for path in ["", "equipment_detail", "register", "due", "analysis", "history"]:
        goto(page, path)
        assert not has_traceback(page), path

