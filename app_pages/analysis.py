import altair as alt
import pandas as pd
import streamlit as st

from app_pages._components import cached_analysis, cached_equipment, db_url, equipment_label, load

st.title("고장 분석")

equipment = load(cached_equipment, db_url())
if not equipment:
    st.stop()

S = st.session_state
S.setdefault("ana_months", 6)
c1, c2 = st.columns([3, 2])
with c1:
    months = st.segmented_control("분석 기간", [1, 3, 6, 12], format_func=lambda m: f"최근 {m}개월", key="ana_months",
                                  required=True, width="stretch")
with c2:
    eq_id = st.selectbox("설비", [None] + [e["equipment_id"] for e in equipment], format_func=equipment_label(equipment),
                         key="ana_equipment")

data = load(cached_analysis, db_url(), months, eq_id, spinner="분석 중…")
if data is None:
    st.stop()

s = data["summary"]
st.caption(f"기간 {data['period']['from']} ~ {data['period']['to']} (기준일 = 최근 가동로그일)")
if s["total"] == 0:
    st.info("선택한 기간·설비에 작업 이력이 없습니다.", icon="🔍")
    st.stop()

m1, m2, m3, m4 = st.columns(4)
m1.metric("전체 작업", f"{s['total']}건", border=True)
m2.metric("돌발고장", f"{s['breakdown']}건", border=True)
m3.metric("예방보전 비율", f"{s['pm_ratio']}%", delta=f"{s['pm_ratio'] - s['pm_ratio_target']:+.1f}%p (목표 70%)",
          border=True)
m4.metric("교체 부품비", f"{s['parts_cost']:,}원", border=True, help="교체 이력 × 파트 단가(데모용 가정값). 인건비 제외")

# ---------- 해석 카드 ----------
st.subheader("분석 결과 해석")
st.caption("문제 → 추정 원인 → 권장 조치 → 확인 방법. 원인은 규칙 기반 **추정**이므로 확인 방법으로 반드시 검증하세요.")
if not data["findings"]:
    st.success("눈에 띄는 반복고장·조기고장·편중 현상이 없습니다.", icon="✅")
for i, f in enumerate(data["findings"]):
    with st.container(border=True, key=f"finding_card_{i}"):
        st.badge(f"심각도 {f['심각도']}", color="red" if f["심각도"] == "높음" else "orange")
        st.markdown(f"**문제** — {f['문제']}")
        st.markdown(f"**추정 원인** :orange-badge[추정] {f['추정 원인'].removeprefix('(추정) ')}")
        st.markdown(f"**권장 조치** — {f['권장 조치']}")
        st.markdown(f"**확인 방법** — {f['확인 방법']}")

# ---------- 차트 ----------
c1, c2 = st.columns(2)
with c1:
    st.markdown("**유닛별 돌발고장**")
    by_unit = pd.DataFrame(list(data["breakdowns_by_unit"].items()), columns=["유닛", "돌발 건수"])
    if by_unit.empty:
        st.info("돌발고장이 없습니다.")
    else:
        st.altair_chart(
            alt.Chart(by_unit).mark_bar().encode(
                x=alt.X("유닛:N", sort="-y", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("돌발 건수:Q", title="건수", axis=alt.Axis(tickMinStep=1)),
                tooltip=["유닛", "돌발 건수"]),
            key="chart_by_unit")
with c2:
    st.markdown("**월별 예방보전 비율**")
    monthly = pd.DataFrame(data["monthly_pm_ratio"])
    line = alt.Chart(monthly).mark_line(point=True).encode(
        x=alt.X("month:N", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("pm_ratio:Q", title="예방보전 비율(%)", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("month:N", title="월"), alt.Tooltip("pm_ratio:Q", title="비율(%)"),
                 alt.Tooltip("preventive:Q", title="예방"), alt.Tooltip("breakdown:Q", title="돌발")])
    target = alt.Chart(pd.DataFrame({"y": [s["pm_ratio_target"]]})).mark_rule(strokeDash=[6, 4], color="gray").encode(y="y:Q")
    label = alt.Chart(pd.DataFrame({"y": [s["pm_ratio_target"]], "t": ["목표 70%"]})).mark_text(
        align="left", dx=4, dy=-6, color="gray").encode(y="y:Q", text="t:N")
    st.altair_chart(line + target + label, key="chart_pm_ratio")

# ---------- 상세 목록 ----------
with st.expander(f"반복고장 {len(data['repeat_failures'])}건 (같은 설비·파트 돌발 90일 내 재발)"):
    if data["repeat_failures"]:
        st.dataframe(pd.DataFrame([{
            "설비": r["equipment_id"], "파트": f"{r['part_id']} {r['part_name']}", "횟수": r["count"],
            "최단 재발(일)": r["min_gap_days"], "돌발 일자": ", ".join(str(d) for d in r["dates"]),
        } for r in data["repeat_failures"]]), hide_index=True, key="repeat_table")
    else:
        st.info("해당 없음")
with st.expander(f"조기고장 {len(data['early_failures'])}건 (교체주기의 50% 미만에서 돌발)"):
    if data["early_failures"]:
        st.dataframe(pd.DataFrame([{
            "작업일": e["log_date"], "설비": e["equipment_id"], "파트": f"{e['part_id']} {e['part_name']}",
            "조치": e["action_type"], "직전 교체": e["last_reset"], "사용률(%)": e["usage_pct"],
        } for e in data["early_failures"]]), hide_index=True, key="early_table")
    else:
        st.info("해당 없음")
for note in data["notes"]:
    st.caption(note)
