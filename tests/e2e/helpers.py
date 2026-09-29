"""E2E 조작·검증 헬퍼."""

from scripts.common import ROOT, fetch_all, read_connection
from tests.e2e.conftest import BASE_URL, DB_URL, SHOTS


def settle(page, timeout: int = 20000) -> None:
    """Streamlit 재실행(스크립트 실행 표시)과 스피너가 끝날 때까지 기다린다."""
    page.wait_for_timeout(300)
    page.wait_for_function(
        "() => !document.querySelector('[data-testid=\"stStatusWidget\"]') && "
        "!document.querySelector('[data-testid=\"stSpinner\"]')", timeout=timeout)
    page.wait_for_timeout(200)


def goto(page, path: str = "") -> None:
    page.goto(f"{BASE_URL.rstrip('/')}/{path}")
    page.wait_for_selector('[data-testid="stAppViewContainer"]')
    page.wait_for_selector("h1")
    settle(page)


def button(page, key: str):
    return page.locator(f".st-key-{key} button").first


def click(page, key: str) -> None:
    button(page, key).click()
    settle(page)


def fill(page, key: str, text: str) -> None:
    box = page.locator(f".st-key-{key} input")
    box.fill(text)
    box.press("Enter")
    settle(page)


def value(page, key: str) -> str:
    """selectbox(react-aria ComboBox)의 현재 선택값 표시 문자열."""
    return page.locator(f".st-key-{key} input[role='combobox']").input_value()


def open_select(page, key: str) -> None:
    page.locator(f".st-key-{key} input[role='combobox']").click()
    page.wait_for_selector("[role='option']")


def choose(page, key: str, option: str) -> None:
    """목록은 화면에 보이는 항목만 그리므로 입력칸에 글자를 쳐서 거른 뒤 고른다."""
    box = page.locator(f".st-key-{key} input[role='combobox']")
    box.click()
    box.fill(option)
    page.get_by_role("option", name=option, exact=True).click()
    settle(page)


def segment(page, key: str, label: str) -> None:
    page.locator(f".st-key-{key}").get_by_role("radio", name=label, exact=True).click()
    settle(page)


def active_segment(page, key: str) -> str | None:
    loc = page.locator(f".st-key-{key} [role='radio'][aria-checked='true']")
    return loc.inner_text().strip() if loc.count() else None


def alerts(page) -> list[str]:
    return [t.strip() for t in page.locator('[data-testid="stAlert"]').all_inner_texts()]


def has_traceback(page) -> bool:
    return page.locator('[data-testid="stException"]').count() > 0


def shot(page, name: str, full: bool = False) -> str:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"{name}.png"
    page.screenshot(path=str(path), full_page=full)
    return str(path.relative_to(ROOT))


def db_one(sql: str, params: dict | None = None) -> dict:
    with read_connection(DB_URL) as conn:
        return fetch_all(conn, sql, params)[0]


def repair_count() -> int:
    return db_one("SELECT COUNT(*) AS n FROM repair_logs")["n"]


def stock(part_id: str) -> int:
    return db_one("SELECT stock_qty FROM parts WHERE part_id = :p", {"p": part_id})["stock_qty"]


def parse_text(page, text: str) -> None:
    goto(page, "register")
    fill(page, "nl_input", text)
    click(page, "parse_btn")
