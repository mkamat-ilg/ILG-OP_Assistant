import streamlit as st
import pandas as pd

from src.pdf_utils import pdf_bytes_to_images, image_bytes_to_images, render_doc_viewer
from src.openai_client import extract_step1_builder_selections, extract_step2_rooms_transitions

APP_TITLE = "Order Processing – Steps 0–2"

# ---------------------------
# Session State
# ---------------------------
def init_state():
    st.session_state.setdefault("step_idx", 0)
    st.session_state.setdefault("verified", {0: False, 1: False, 2: False})

    st.session_state.setdefault("selection_file", None)  # dict: {name, ext, bytes}
    st.session_state.setdefault("floorplan_file", None)

    st.session_state.setdefault("step1_df", None)
    st.session_state.setdefault("step2_rooms_df", None)
    st.session_state.setdefault("step2_trans_df", None)

init_state()

def go(step: int):
    st.session_state.step_idx = step
    st.rerun()

def require_verified(step: int):
    if not st.session_state.verified.get(step, False):
        st.error(f"You must verify Step {step} before proceeding.")
        st.stop()

# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)

with st.sidebar:
    st.subheader("Steps (gated)")
    labels = [
        "0. Upload Selection Sheet + Floorplan",
        "1. Extract Builder Selections (Room | Trade | Material Description)",
        "2. Extract Rooms + Transitions from Floorplan",
    ]
    for i, label in enumerate(labels):
        done = "✅" if st.session_state.verified.get(i) else "⬜"
        disabled = (i > 0 and not st.session_state.verified.get(i-1, False))
        if st.button(f"{done} {label}", use_container_width=True, disabled=disabled):
            go(i)

# ---------------------------
# Step 0
# ---------------------------
if st.session_state.step_idx == 0:
    st.header("Step 0 – Mandatory uploads")

    c1, c2 = st.columns(2)

    with c1:
        sel = st.file_uploader(
            "Upload Selection Sheet (PDF/image preferred)",
            type=["pdf", "png", "jpg", "jpeg"],
            key="u_sel",
        )
        if sel:
            st.session_state.selection_file = {
                "name": sel.name,
                "ext": sel.name.split(".")[-1].lower(),
                "bytes": sel.getvalue(),
            }

    with c2:
        fp = st.file_uploader(
            "Upload Floorplan (PDF/image preferred)",
            type=["pdf", "png", "jpg", "jpeg"],
            key="u_fp",
        )
        if fp:
            st.session_state.floorplan_file = {
                "name": fp.name,
                "ext": fp.name.split(".")[-1].lower(),
                "bytes": fp.getvalue(),
            }

    has_sel = st.session_state.selection_file is not None
    has_fp = st.session_state.floorplan_file is not None

    if has_sel and has_fp:
        st.success("Both required documents uploaded.")
        if st.button("Proceed to Step 1", type="primary"):
            st.session_state.verified[0] = True
            go(1)
    else:
        st.info("Upload both documents to continue.")

    st.stop()

# ---------------------------
# Step 1
# ---------------------------
if st.session_state.step_idx == 1:
    require_verified(0)
    st.header("Step 1 – Builder Selections → Flooring Scope")

    sel_file = st.session_state.selection_file

    left, right = st.columns([1, 1])

    with right:
        st.subheader("Selection Sheet (scroll + zoom for verification)")
        render_doc_viewer(sel_file, key_prefix="sel_view")

    with left:
        st.subheader("Extracted output (editable)")
        st.caption("Expected columns: Room | Trade | Material Description")

        if st.session_state.step1_df is None:
            st.session_state.step1_df = pd.DataFrame(columns=["Room", "Trade", "Material Description"])

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("Run OpenAI extraction", type="primary"):
                # Convert doc to images
                if sel_file["ext"] == "pdf":
                    imgs = pdf_bytes_to_images(sel_file["bytes"])
                else:
                    imgs = image_bytes_to_images(sel_file["bytes"])
                rows = extract_step1_builder_selections(imgs)
                st.session_state.step1_df = pd.DataFrame(rows, columns=["Room", "Trade", "Material Description"])

        with colB:
            if st.button("Reset table"):
                st.session_state.step1_df = pd.DataFrame(columns=["Room", "Trade", "Material Description"])

        edited = st.data_editor(
            st.session_state.step1_df,
            num_rows="dynamic",
            use_container_width=True,
            key="step1_editor",
        )
        st.session_state.step1_df = edited

        st.divider()
        if st.button("I have verified the Builder Selections. Move to Step 2", type="primary"):
            st.session_state.verified[1] = True
            go(2)

    st.stop()

# ---------------------------
# Step 2
# ---------------------------
if st.session_state.step_idx == 2:
    require_verified(1)
    st.header("Step 2 – Floorplan → Rooms + Transitions")

    fp_file = st.session_state.floorplan_file

    left, right = st.columns([1, 1])

    with right:
        st.subheader("Floorplan (scroll + zoom for verification)")
        render_doc_viewer(fp_file, key_prefix="fp_view")

    with left:
        st.subheader("Rooms (editable)")
        if st.session_state.step2_rooms_df is None:
            st.session_state.step2_rooms_df = pd.DataFrame(columns=["Room"])

        if st.session_state.step2_trans_df is None:
            st.session_state.step2_trans_df = pd.DataFrame(columns=["Room", "Adjoining Room", "Transition needed"])

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("Run OpenAI extraction", type="primary"):
                if fp_file["ext"] == "pdf":
                    imgs = pdf_bytes_to_images(fp_file["bytes"])
                else:
                    imgs = image_bytes_to_images(fp_file["bytes"])
                rooms, transitions = extract_step2_rooms_transitions(imgs)
                st.session_state.step2_rooms_df = pd.DataFrame(rooms, columns=["Room"])
                st.session_state.step2_trans_df = pd.DataFrame(
                    transitions,
                    columns=["Room", "Adjoining Room", "Transition needed"],
                )

        with colB:
            if st.button("Reset outputs"):
                st.session_state.step2_rooms_df = pd.DataFrame(columns=["Room"])
                st.session_state.step2_trans_df = pd.DataFrame(columns=["Room", "Adjoining Room", "Transition needed"])

        rooms_edit = st.data_editor(
            st.session_state.step2_rooms_df,
            num_rows="dynamic",
            use_container_width=True,
            key="step2_rooms_editor",
        )
        st.session_state.step2_rooms_df = rooms_edit

        st.subheader("Room | Adjoining Room | Transition needed (editable)")
        trans_edit = st.data_editor(
            st.session_state.step2_trans_df,
            num_rows="dynamic",
            use_container_width=True,
            key="step2_trans_editor",
        )
        st.session_state.step2_trans_df = trans_edit

        st.divider()
        if st.button("I have verified the Rooms. Move to Step 3", type="primary"):
            st.session_state.verified[2] = True
            st.success("Steps 0–2 complete. Next: Step 3 merge (not included in this drop).")

    st.stop()
