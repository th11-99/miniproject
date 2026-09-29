import pandas as pd
import streamlit as st

from app_pages._components import (STATUS_ICON, assumed_value_notice, cached_detail, cached_equipment, db_url,
                                   due_frame, equipment_label, load, style_status)

st.title("설비 상세")

equipment = load(cached_equipment, db_url())
if not equipment:
    st.stop()
ids = [e["equipment_id"] for e in equipment]
if st.session_state.get("detail_equipment_select") not in ids:
    st.session_state["detail_equipment_select"] = ids[0]
eq_id = st.selectbox("설비", ids, format_func=equipment_label(equipment), key="detail_equipment_select")

detail = load(cached_detail, db_url(), eq_id)
if detail is None:
    st.stop()

eq = detail["equipment"]
st.caption(f"{eq['name']} · 도입 {eq['installed_at']} · 기준일 {detail['reference_date']} (최근 가동로그일)")
assumed_value_notice()


def _tab_label(asm: dict) -> str:
    statuses = {p["status"] for p in asm["parts"]}
    mark = STATUS_ICON["초과"] if "초과" in statuses else STATUS_ICON["임박"] if "임박" in statuses else ""
    return f"{asm['name']} {mark}".strip()


assemblies = detail["assemblies"]
tabs = st.tabs([_tab_label(a) for a in assemblies], key="detail_tabs")
for tab, asm in zip(tabs, assemblies):
    with tab:
        st.caption(f"{asm['assembly_code']} · {asm['description']}")
        with st.container(key=f"spec_{asm['assembly_code']}"):
            for col, spec in zip(st.columns(3), asm["specs"]):
                col.metric(spec["label"], f"{spec['value']} {spec['unit']}".strip(), border=True)

        st.markdown("**장착 파트 교체 도래 (30일 기준)**")
        if asm["parts"]:
            st.dataframe(style_status(due_frame(asm["parts"]).drop(columns=["설비", "구조부"])),
                         hide_index=True, key=f"detail_parts_{asm['assembly_code']}",
                         column_config={"사용률(%)": st.column_config.NumberColumn(format="%.1f%%")})
        else:
            st.info("이 구조부에 등록된 관리 파트가 없습니다. (기어박스·운전조작반 소모품 추가 여부는 PRD 미결 사항)")

        st.markdown("**최근 이력**")
        if asm["recent_logs"]:
            st.dataframe(pd.DataFrame([{
                "작업일": log["log_date"], "파트": f"{log['part_id']} {log['part_name']}", "조치": log["action_type"],
                "구분": "돌발" if log["is_breakdown"] else "예방", "내용": log["description"],
            } for log in asm["recent_logs"]]), hide_index=True, key=f"detail_logs_{asm['assembly_code']}")
        else:
            st.info("최근 이력이 없습니다.")
