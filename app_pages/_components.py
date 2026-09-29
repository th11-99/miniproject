"""페이지 공통 조각. 페이지에는 계산 로직을 두지 않고 scripts/ 함수를 호출·표시만 한다."""

import pandas as pd
import streamlit as st

from scripts import analyze as analyze_mod
from scripts import dashboard, due_check, equipment, history
from scripts.common import ASSUMED_VALUE_NOTICE, UserError, get_database_url, is_sqlite

TTL = 60
STATUS_ICON = {"초과": "🔴", "임박": "🟠", "여유": "🟢", "정상": "🟢"}
STATUS_BADGE = {"초과": "red", "임박": "orange", "여유": "green", "정상": "green"}
# 다크·라이트 모두에서 글자가 읽히도록 반투명 배경
STATUS_BG = {"초과": "rgba(255, 75, 75, 0.28)", "임박": "rgba(255, 164, 33, 0.30)", "여유": "rgba(33, 195, 84, 0.22)"}
UNIT_NAMES = analyze_mod.UNIT_NAMES
ASSEMBLY_NAMES = analyze_mod.ASSEMBLY_NAMES
BASIS_NAMES = {"run_hours": "가동시간", "clamp_count": "클램핑 횟수", "index_count": "인덱싱 횟수", "months": "개월"}
ERROR_ICONS = {"조기고장": "🚨", "반복고장": "🔁", "예비품 부족": "📦", "중복 의심": "⚠️"}


def db_url() -> str:
    return get_database_url()


def database_label() -> str:
    return "로컬 SQLite" if is_sqlite(db_url()) else "운영 DB"


# ---------- 캐시된 조회 (url을 키에 넣어 DB가 바뀌면 캐시도 분리) ----------

@st.cache_data(ttl=TTL, show_spinner=False)
def cached_dashboard(url: str) -> dict:
    return dashboard.dashboard_summary(url)


@st.cache_data(ttl=TTL, show_spinner=False)
def cached_due(url: str, equipment_id, unit, days: int, include_all: bool) -> dict:
    return due_check.due_check(equipment_id, unit, days, include_all, url=url)


@st.cache_data(ttl=TTL, show_spinner=False)
def cached_analysis(url: str, months: int, equipment_id) -> dict:
    return analyze_mod.analyze(months, equipment_id, url=url)


@st.cache_data(ttl=TTL, show_spinner=False)
def cached_detail(url: str, equipment_id: str) -> dict:
    return equipment.equipment_detail(equipment_id, url)


@st.cache_data(ttl=TTL, show_spinner=False)
def cached_history(url: str, equipment_id, part_id, date_from, date_to, breakdown) -> dict:
    return history.list_repairs(equipment_id, part_id, date_from, date_to, breakdown, url=url)


@st.cache_data(ttl=TTL, show_spinner=False)
def cached_equipment(url: str) -> list[dict]:
    return equipment.equipment_list(url)


@st.cache_data(ttl=TTL, show_spinner=False)
def cached_parts(url: str) -> list[dict]:
    return equipment.parts_list(url)


def load(fn, *args, spinner: str = "불러오는 중…"):
    """scripts 함수를 호출하고, 실패하면 원인과 해결 방법을 화면에 보여준 뒤 None을 돌려준다."""
    try:
        with st.spinner(spinner):
            return fn(*args)
    except UserError as exc:
        st.error(f"{exc}", icon="⚠️")
    except Exception as exc:  # 예상 못 한 오류도 traceback 대신 안내문으로
        st.error(
            "데이터를 불러오지 못했습니다. DB 연결 상태를 확인하세요.\n\n"
            "- 로컬: `python scripts/init_db.py --yes`로 샘플 DB를 만들었는지 확인\n"
            "- 운영: Streamlit Secrets의 `database.url` 확인\n\n"
            f"오류 종류: `{type(exc).__name__}`",
            icon="🛑",
        )
    return None


# ---------- 표시 조각 ----------

def equipment_label(equipment_list: list[dict]):
    names = {e["equipment_id"]: e["name"] for e in equipment_list}
    return lambda eq_id: f"{eq_id} · {names.get(eq_id, '')}" if eq_id else "전체"


def part_label(parts: list[dict]):
    names = {p["part_id"]: p["part_name"] for p in parts}
    return lambda pid: f"{pid} {names.get(pid, '')}" if pid else "전체"


def assumed_value_notice() -> None:
    st.info(f"**데모용 가정값 안내** — {ASSUMED_VALUE_NOTICE}", icon="ℹ️")


def style_status(df: pd.DataFrame, column: str = "상태"):
    """상태 열만 색으로 표시 (색은 상태 의미로만 사용)."""
    if df.empty or column not in df:
        return df
    return df.style.map(lambda v: f"background-color: {STATUS_BG.get(v, 'transparent')}; font-weight: 600",
                        subset=[column])


def due_frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "상태": r["status"],
        "설비": r["equipment_id"],
        "파트ID": r["part_id"],
        "파트명": r["part_name"],
        "유닛": f"{r['unit']} {UNIT_NAMES[r['unit']]}",
        "구조부": ASSEMBLY_NAMES[r["assembly_code"]],
        "기준": BASIS_NAMES[r["basis"]],
        "사용률(%)": r["usage_pct"],
        "남은 일수": r["days_left"],
        "예상 도래일": r["due_date"],
        "직전 교체": str(r["last_replaced"]) if r["last_replaced"] else "기록 없음(원부품)",
    } for r in rows])


def show_info(info: list[dict], key: str) -> None:
    """log_repair의 info 경고를 눈에 띄게 표시. 조기·반복고장은 빨강, 나머지는 주황."""
    with st.container(key=key):
        if not info:
            st.success("판정 경고 없음 (조기고장·반복고장·예비품 부족·중복 의심 해당 없음)", icon="✅")
            return
        for item in info:
            text = f"**{item['type']}** — {item['message']}"
            icon = ERROR_ICONS.get(item["type"], "⚠️")
            if item["type"] in ("조기고장", "반복고장"):
                st.error(text, icon=icon)
            else:
                st.warning(text, icon=icon)


def clear_cache() -> None:
    st.cache_data.clear()
