import streamlit as st

from app_pages._components import STATUS_BADGE, STATUS_ICON, cached_dashboard, database_label, db_url, load

st.title("대시보드")

data = load(cached_dashboard, db_url())
if data is None:
    st.stop()

st.caption(f"기준일 {data['reference_date']} (최근 가동로그일) · {database_label()}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("교체 초과", f"{data['overdue']}건", border=True, help="교체주기를 넘긴 설비×파트 수")
c2.metric(f"{data['due_days']}일 내 도래", f"{data['due_soon']}건", border=True,
          help=f"{data['due_days']}일 안에 교체주기에 도달할 설비×파트 수")
c3.metric(f"이번 달 돌발고장 ({data['month']})", f"{data['breakdowns_this_month']}건", border=True)
pm, target = data["pm_ratio"], data["pm_ratio_target"]
c4.metric(f"예방보전 비율 (최근 {data['pm_months']}개월)", "-" if pm is None else f"{pm}%",
          delta=None if pm is None else f"{pm - target:+.1f}%p (목표 {target:.0f}%)", border=True)

st.subheader("설비 현황")
st.caption("🔴 교체 초과 있음 · 🟠 30일 내 도래 있음 · 🟢 정상 — 설비를 누르면 상세 화면으로 이동합니다.")

equipment = data["equipment"]
for start in range(0, len(equipment), 4):
    cols = st.columns(4)
    for col, e in zip(cols, equipment[start:start + 4]):
        eq_id = e["equipment_id"]
        with col.container(border=True, key=f"eq_card_{eq_id}"):
            st.markdown(f"#### {STATUS_ICON[e['status']]} {eq_id}")
            st.caption(e["name"])
            b1, b2 = st.columns(2)
            with b1:
                st.badge(f"초과 {e['초과']}", color=STATUS_BADGE["초과"] if e["초과"] else "gray")
            with b2:
                st.badge(f"임박 {e['임박']}", color=STATUS_BADGE["임박"] if e["임박"] else "gray")
            if st.button("상세 보기", key=f"eq_btn_{eq_id}", width="stretch"):
                st.session_state["detail_equipment_select"] = eq_id
                st.switch_page("app_pages/equipment_detail.py")

if data["top_findings"]:
    st.subheader("주요 분석 결과")
    for f in data["top_findings"]:
        st.markdown(f"- **[{f['심각도']}]** {f['문제']}")
    st.page_link("app_pages/analysis.py", label="고장 분석에서 원인·조치 보기", icon=":material/insights:")
