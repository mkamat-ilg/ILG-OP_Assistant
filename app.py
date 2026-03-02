import streamlit as st

from src.steps.step0_uploads import render_step0
from src.steps.step1_selection_extract import render_step1
from src.steps.step2_floorplan_extract import render_step2
from src.steps.step3_merge import render_step3
from src.steps.step4_takeoff_crossref import render_step4
from src.steps.step5_sap_match import render_step5
from src.steps.step6_sundries_labor import render_step6

STEPS = [
    ("Step 0", render_step0),
    ("Step 1", render_step1),
    ("Step 2", render_step2),
    ("Step 3", render_step3),
    ("Step 4", render_step4),
    ("Step 5", render_step5),
    ("Step 6", render_step6),
]

def init_state():
    st.session_state.setdefault("step_idx", 0)
    st.session_state.setdefault("verified", {i: False for i in range(len(STEPS))})
    # payload slots
    st.session_state.setdefault("selection_pdf_bytes", None)
    st.session_state.setdefault("floorplan_pdf_bytes", None)
    st.session_state.setdefault("step1_df", None)
    st.session_state.setdefault("step2_rooms_df", None)
    st.session_state.setdefault("step2_adj_df", None)
    st.session_state.setdefault("step3_a_df", None)
    st.session_state.setdefault("step3_b_df", None)
    st.session_state.setdefault("step4_c_df", None)
    st.session_state.setdefault("step4_d_df", None)
    st.session_state.setdefault("step5_df", None)
    st.session_state.setdefault("step6_df", None)

init_state()

st.set_page_config(layout="wide")
st.title("Order Processing – Multi-step")

left, right = st.columns([1, 3])
with left:
    st.subheader("Progress")
    for i, (label, _) in enumerate(STEPS):
        done = "✅" if st.session_state["verified"].get(i) else "⬜"
        if st.button(f"{done} {label}", use_container_width=True, disabled=(i > st.session_state["step_idx"])):
            st.session_state["step_idx"] = i

step_label, step_fn = STEPS[st.session_state["step_idx"]]
st.divider()
step_fn()
