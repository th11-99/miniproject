import streamlit as st

from app_pages._components import (UNIT_NAMES, assumed_value_notice, cached_due, cached_equipment, db_url, due_frame,
                                   equipment_label, load, style_status)
from scripts.due_check import csv_bytes

st.title("교체 도래")
assumed_value_notice()

equipment = load(cached_equipment, db_url())
if not equipment:
    st.stop()

S = st.session_state
S.setdefault("due_days", 30)
c1, c2, c3 = st.columns([2, 2, 3])
with c1:
    eq_id = st.selectbox("설비", [None] + [e["equipment_id"] for e in equipment], format_func=equipment_label(equipment),
                         key="due_equipment")
with c2:
    unit = st.selectbox("유닛", [None] + list(UNIT_NAMES), format_func=lambda u: f"{u} {UNIT_NAMES[u]}" if u else "전체",
                        key="due_unit")
with c3:
    days = st.segmented_control("임박 기준", [7, 30, 90], format_func=lambda d: f"{d}일 이내", key="due_days",
                                required=True, width="stretch")
include_all = st.toggle("여유 상태까지 모두 보기", key="due_all")

data = load(cached_due, db_url(), eq_id, unit, days, include_all)
if data is None:
    st.stop()

s = data["summary"]
st.caption(f"기준일 {data['reference_date']} (최근 가동로그일) · 사용량 = 직전 교체 이후 누적 증가분, 교체 기록이 없으면 도입 이후 전체")
m1, m2, m3 = st.columns(3)
m1.metric("🔴 초과", f"{s['초과']}건", border=True)
m2.metric(f"🟠 {days}일 이내", f"{s['임박']}건", border=True)
m3.metric("🟢 여유", f"{s['여유']}건", border=True)

rows = data["rows"]
if not rows:
    st.info("조건에 맞는 도래 파트가 없습니다. 필터를 바꾸거나 '여유 상태까지 모두 보기'를 켜 보세요.", icon="🔍")
else:
    st.dataframe(style_status(due_frame(rows)), hide_index=True, key="due_table",
                 column_config={"사용률(%)": st.column_config.NumberColumn(format="%.1f%%"),
                                "남은 일수": st.column_config.NumberColumn(help="음수 = 초과 일수")})
    st.download_button("CSV 저장 (엑셀용)", csv_bytes(rows),
                       file_name=f"due_{data['reference_date'].strftime('%Y%m%d')}.csv", mime="text/csv",
                       key="due_download", width="stretch", icon=":material/download:")
