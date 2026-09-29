"""CNC 선반 보전관리 — Streamlit 진입점.

  streamlit run streamlit_app.py
"""

import streamlit as st

from scripts.common import DEFAULT_URL, get_database_url, sqlite_path
from scripts.init_db import build_database

st.set_page_config(page_title="CNC 보전관리", page_icon="🛠️", layout="wide")


@st.cache_resource
def ensure_demo_db() -> bool:
    """시연용: 다른 DB를 지정하지 않았고(DATABASE_URL·secrets 없음) 기본 DB 파일도 없으면 샘플 DB를 만든다.

    Streamlit Community Cloud에는 DB 파일이 올라가지 않으므로(.gitignore) 첫 실행 때 여기서 생성된다.
    이미 있는 DB는 절대 지우지 않는다. 앱이 재시작되면 Cloud의 파일이 초기화되어 등록 이력도 사라진다.
    """
    if get_database_url() != DEFAULT_URL or sqlite_path(DEFAULT_URL).exists():
        return False
    build_database(DEFAULT_URL)
    return True


demo_created = ensure_demo_db()

pages = [
    st.Page("app_pages/dashboard.py", title="대시보드", icon=":material/dashboard:", default=True),
    st.Page("app_pages/equipment_detail.py", title="설비 상세", icon=":material/precision_manufacturing:"),
    st.Page("app_pages/register.py", title="이력 등록", icon=":material/edit_note:"),
    st.Page("app_pages/due.py", title="교체 도래", icon=":material/event_upcoming:"),
    st.Page("app_pages/analysis.py", title="고장 분석", icon=":material/insights:"),
    st.Page("app_pages/history.py", title="이력 조회", icon=":material/history:"),
]

with st.sidebar:
    st.caption("CNC 선반 보전관리 · 교체주기·단가·사양은 데모용 가정값")
    if demo_created:
        st.caption("시연용 샘플 DB를 새로 만들었습니다. 앱이 재시작되면 등록 이력은 초기화됩니다.")

st.navigation(pages).run()
