from datetime import date, timedelta

import pandas as pd
import streamlit as st

from app_pages._components import (UNIT_NAMES, cached_equipment, cached_history, cached_parts, db_url,
                                   equipment_label, load, part_label)

st.title("이력 조회")

equipment = load(cached_equipment, db_url())
parts = load(cached_parts, db_url())
if not equipment or not parts:
    st.stop()

S = st.session_state
S.setdefault("hist_dates", (date.today() - timedelta(days=365), date.today()))
S.setdefault("hist_breakdown", "전체")
c1, c2 = st.columns(2)
with c1:
    eq_id = st.selectbox("설비", [None] + [e["equipment_id"] for e in equipment], format_func=equipment_label(equipment),
                         key="hist_equipment")
with c2:
    part_id = st.selectbox("파트", [None] + [p["part_id"] for p in parts], format_func=part_label(parts),
                           key="hist_part")
c1, c2 = st.columns(2)
with c1:
    dates = st.date_input("기간", key="hist_dates", format="YYYY-MM-DD")
with c2:
    kind = st.segmented_control("구분", ["전체", "돌발", "예방"], key="hist_breakdown", required=True, width="stretch")

if not isinstance(dates, tuple) or len(dates) != 2:
    st.info("기간의 시작일과 종료일을 모두 선택하세요.", icon="📅")
    st.stop()
breakdown = {"전체": None, "돌발": True, "예방": False}[kind]

data = load(cached_history, db_url(), eq_id, part_id, dates[0], dates[1], breakdown)
if data is None:
    st.stop()

if not data["rows"]:
    st.info("조건에 맞는 이력이 없습니다.", icon="🔍")
    st.stop()

note = f" — 최근 {data['limit']}건만 표시" if data["truncated"] else ""
st.caption(f"{data['row_count']}건{note} · 작업일 최신순. 표 머리글을 눌러 정렬하고, 표 오른쪽 위 🔍로 검색할 수 있습니다.")
st.dataframe(pd.DataFrame([{
    "ID": r["id"], "작업일": r["log_date"], "설비": r["equipment_id"], "파트ID": r["part_id"], "파트명": r["part_name"],
    "유닛": UNIT_NAMES[r["unit"]], "장착 위치": r["assembly"], "조치": r["action_type"],
    "구분": "돌발" if r["is_breakdown"] else "예방", "내용": r["description"],
} for r in data["rows"]]), hide_index=True, key="history_table",
    column_config={"ID": st.column_config.NumberColumn(format="%d")})
