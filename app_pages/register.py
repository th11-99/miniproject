"""이력 등록: 자연어 해석 → 입력 확인·수정 → 미리보기(dry-run) → "등록할까요?" 확인 → 등록.

- 등록되는 값은 항상 "마지막 미리보기에 쓴 값"이다. 미리보기 뒤 입력이 바뀌면 미리보기를 무효화한다.
  (st.form은 제출 전 변경을 앱이 알 수 없어 무효화 규칙을 지킬 수 없으므로 쓰지 않는다)
- 미리보기마다 1회용 토큰을 발급하고, 등록에 쓴 토큰은 다시 쓸 수 없게 해 연타·재실행 중복 등록을 막는다.
"""

import uuid
from datetime import date

import pandas as pd
import streamlit as st

from app_pages._components import (ASSEMBLY_NAMES, UNIT_NAMES, cached_equipment, cached_parts, clear_cache, db_url,
                                   equipment_label, load, part_label, show_info)
from scripts import normalize
from scripts.common import UserError
from scripts.log_repair import log_repair
from scripts.schema import ACTION_TYPES

S = st.session_state
S.setdefault("used_tokens", set())
# 위젯 값은 모두 Session State로 관리한다 (index/value 인자와 함께 쓰면 Streamlit 경고가 뜬다)
for _key in ("reg_equipment", "reg_part", "reg_unit", "reg_action", "reg_breakdown"):
    S.setdefault(_key, None)
S.setdefault("reg_date", date.today())
S.setdefault("reg_desc", "")


def current_params() -> dict | None:
    """지금 화면에 입력된 등록 값. 필수 값이 비었으면 None."""
    if not all(S.get(k) for k in ("reg_equipment", "reg_part", "reg_action", "reg_breakdown")):
        return None
    return {"equipment": S["reg_equipment"], "part": S["reg_part"], "action": S["reg_action"],
            "breakdown": S["reg_breakdown"] == "돌발", "log_date": S["reg_date"], "desc": (S.get("reg_desc") or "").strip()}

st.title("이력 등록")
st.caption("현장 표현 그대로 입력하면 설비·파트·조치를 해석해 채워 줍니다. 미리보기로 확인한 내용만 등록됩니다.")

equipment = load(cached_equipment, db_url())
parts = load(cached_parts, db_url())
if not equipment or not parts:
    st.stop()
eq_ids = [e["equipment_id"] for e in equipment]
part_ids = [p["part_id"] for p in parts]
part_by_id = {p["part_id"]: p for p in parts}


# ---------- 1. 자연어 해석 ----------

def do_parse() -> None:
    S.pop("parse_error", None)
    S.pop("preview", None)
    text = S.get("nl_input", "").strip()
    if not text:
        S["parse_error"] = "작업 내용을 입력하세요. 예: 3번기 주축 베어링 소음나서 교체"
        return
    try:
        parsed = normalize.parse(text, db_url())
    except UserError as exc:
        S["parse_error"] = str(exc)
        return
    S["parsed"] = parsed
    candidates = [c["part_id"] for c in parsed["parts"]["candidates"]]
    S["reg_equipment"] = parsed["equipment"]
    S["reg_part"] = candidates[0] if parsed["parts"]["status"] == "one" else None
    S["reg_unit"] = None
    S["reg_action"] = parsed["action"]
    S["reg_breakdown"] = {True: "돌발", False: "예방"}.get(parsed["breakdown"])
    S["reg_date"] = min(parsed["date"] or date.today(), date.today())
    S["reg_desc"] = text


def reset_form() -> None:
    for key in ("reg_equipment", "reg_part", "reg_unit", "reg_action", "reg_breakdown"):
        S[key] = None
    S["reg_date"], S["reg_desc"], S["nl_input"] = date.today(), "", ""
    for key in ("parsed", "preview", "parse_error", "preview_error", "last_result"):
        S.pop(key, None)


with st.container(border=True, key="nl_box"):
    st.text_input("작업 내용 (현장 표현)", key="nl_input", placeholder="예: 3번기 주축 베어링 소음나서 교체")
    c1, c2 = st.columns([3, 1])
    c1.button("해석하기", key="parse_btn", on_click=do_parse, type="primary", width="stretch")
    c2.button("처음부터", key="reset_btn", on_click=reset_form, width="stretch")
    if S.get("parse_error"):
        st.error(S["parse_error"], icon="⚠️")
    parsed = S.get("parsed")
    questions_box = st.container(key="parse_questions")  # 필수 입력이 다 채워지면 비운다 (아래에서 채움)

# ---------- 2. 입력 확인·수정 ----------

st.subheader("등록 내용 확인")
mode = parsed["parts"]["status"] if parsed else "manual"

c1, c2 = st.columns(2)
with c1:
    st.selectbox("설비", eq_ids, placeholder="설비 선택", format_func=equipment_label(equipment), key="reg_equipment")
with c2:
    if mode == "many":
        options = [c["part_id"] for c in parsed["parts"]["candidates"]]
        if S.get("reg_part") not in options:
            S["reg_part"] = None
        st.radio("파트 후보 중 선택", options, format_func=part_label(parts), key="reg_part")
    elif mode == "none":
        st.warning("파트를 찾지 못했습니다. 유닛을 고른 뒤 파트를 선택하세요.", icon="🔎")
        st.selectbox("유닛", list(UNIT_NAMES), placeholder="유닛 선택",
                     format_func=lambda u: f"{u} {UNIT_NAMES[u]}", key="reg_unit",
                     on_change=lambda: S.update(reg_part=None))
        unit = S.get("reg_unit")
        options = [pid for pid in part_ids if unit and part_by_id[pid]["unit"] == unit]
        if S.get("reg_part") not in options:
            S["reg_part"] = None
        st.selectbox("파트", options, placeholder="파트 선택", format_func=part_label(parts),
                     key="reg_part", disabled=not unit)
    else:
        st.selectbox("파트", part_ids, placeholder="파트 선택", format_func=part_label(parts), key="reg_part")

st.segmented_control("조치 유형", ACTION_TYPES, key="reg_action", width="stretch")
c1, c2 = st.columns(2)
with c1:
    st.segmented_control("구분", ["돌발", "예방"], key="reg_breakdown", width="stretch",
                         help="돌발 = 알람·정지·파손·누유·불량 등 예정에 없던 고장 대응 / 예방 = 주기 도래·PM·정기 작업")
with c2:
    st.date_input("작업일", key="reg_date", max_value=date.today(), format="YYYY-MM-DD")
st.text_input("작업 내용 메모", key="reg_desc")

selected_part = part_by_id.get(S.get("reg_part"))
if selected_part:
    st.caption(f"선택 파트: {selected_part['part_id']} {selected_part['part_name']} · "
               f"유닛 {UNIT_NAMES[selected_part['unit']]} · 장착 위치 {ASSEMBLY_NAMES[selected_part['assembly_code']]} · "
               f"재고 {selected_part['stock_qty']}개 (안전재고 {selected_part['safety_stock']})")

missing = [label for key, label in (("reg_equipment", "설비"), ("reg_part", "파트"), ("reg_action", "조치 유형"),
                                    ("reg_breakdown", "구분(돌발/예방)")) if not S.get(key)]
current = current_params()
if parsed and parsed["questions"] and missing:
    with questions_box:
        st.caption("해석 결과 확인이 필요합니다. 아래에서 채워 주세요.")
        for q in parsed["questions"]:
            st.warning(q, icon="❓")


# ---------- 3. 미리보기 ----------

def do_preview() -> None:
    S.pop("preview_error", None)
    params = current_params()  # 콜백 시점의 최신 입력값
    if params is None:
        S["preview_error"] = "필수 입력(설비·파트·조치 유형·구분)을 모두 채워 주세요."
        return
    try:
        result = log_repair(**params, dry_run=True, url=db_url())
    except UserError as exc:
        S["preview_error"] = str(exc)
        S.pop("preview", None)
        return
    S["preview"] = {"params": params, "result": result, "token": uuid.uuid4().hex}
    S.pop("last_result", None)


if missing:
    st.info(f"입력이 더 필요합니다: {', '.join(missing)}", icon="✏️")
st.button("미리보기", key="preview_btn", on_click=do_preview, disabled=bool(missing), type="primary", width="stretch")
if S.get("preview_error"):
    st.error(S["preview_error"], icon="⚠️")

preview = S.get("preview")
stale = preview is not None and preview["params"] != current
if preview:
    st.subheader("미리보기")
    if stale:
        st.warning("미리보기 후 입력이 바뀌었습니다. 바뀐 내용으로 다시 **미리보기**를 눌러 주세요.", icon="🔄")
    row = preview["result"]["row"]
    st.dataframe(pd.DataFrame([{
        "작업일": row["log_date"], "설비": f"{row['equipment_id']} {row['equipment_name']}",
        "파트": f"{row['part_id']} {row['part_name']}", "유닛": UNIT_NAMES[row["unit"]],
        "장착 위치": ASSEMBLY_NAMES[row["assembly_code"]], "조치": row["action_type"],
        "구분": "돌발" if row["is_breakdown"] else "예방", "내용": row["description"],
        "재고 변화": f"{row['stock_before']} → {row['stock_after']}",
    }]), hide_index=True, key="preview_table")
    show_info(preview["result"]["info"], key="info_banner")


# ---------- 4. 확인 후 등록 ----------

def register_now() -> None:
    p = S.get("preview")
    if not p or p["token"] in S["used_tokens"]:
        return  # 이미 처리된 미리보기 (연타·재실행)
    S["used_tokens"].add(p["token"])
    try:
        result = log_repair(**p["params"], dry_run=False, url=db_url())
    except UserError as exc:
        S["used_tokens"].discard(p["token"])
        S["register_error"] = str(exc)
        return
    S["last_result"] = result
    S.pop("preview", None)
    clear_cache()


def close_confirm() -> None:
    S["confirm_open"] = False


# 확인 창이 열려 있는지는 세션에 둔다 (전체 재실행에서도 창과 버튼이 유지되도록)
@st.dialog("등록할까요?", on_dismiss=close_confirm)
def confirm_dialog() -> None:
    p = S["preview"]
    row = p["result"]["row"]
    st.markdown(f"**{row['equipment_id']}** · {row['part_id']} {row['part_name']} · **{row['action_type']}** "
                f"({'돌발' if row['is_breakdown'] else '예방'}) · {row['log_date']}")
    if p["result"]["info"]:
        st.warning(f"경고 {len(p['result']['info'])}건: " + ", ".join(i["type"] for i in p["result"]["info"]), icon="⚠️")
    c1, c2 = st.columns(2)
    if c1.button("등록", key="confirm_register_btn", type="primary", width="stretch"):
        close_confirm()
        register_now()
        st.rerun()
    if c2.button("취소", key="cancel_register_btn", width="stretch"):
        close_confirm()
        st.rerun()


can_register = preview is not None and not stale and preview["token"] not in S["used_tokens"]
if st.button("등록", key="register_btn", disabled=not can_register, width="stretch",
             type="primary" if can_register else "secondary",
             help=None if can_register else "미리보기를 먼저 하세요. 미리보기 후 입력이 바뀌면 다시 미리보기가 필요합니다."):
    S["confirm_open"] = True
if S.get("confirm_open"):
    if can_register:
        confirm_dialog()
    else:
        close_confirm()  # 미리보기가 무효가 되면 확인 창도 닫는다

if S.get("register_error"):
    st.error(f"등록하지 못했습니다: {S.pop('register_error')}", icon="🛑")

last = S.get("last_result")
if last:
    with st.container(border=True, key="result_box"):
        row = last["row"]
        st.success(f"등록 완료 (이력 ID {last['id']}): {row['equipment_id']} {row['part_id']} {row['part_name']} "
                   f"{row['action_type']}", icon="✅")
        if row["action_type"] == "교체":
            st.caption(f"재고 {row['stock_before']} → {row['stock_after']}개로 차감했습니다.")
        show_info(last["info"], key="result_info_banner")
