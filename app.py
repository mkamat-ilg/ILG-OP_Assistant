import os
import streamlit as st
import pandas as pd

from src.pdf_utils import pdf_bytes_to_images, image_bytes_to_images, render_doc_viewer
from src.openai_client import extract_step1_builder_selections, extract_step2_rooms_transitions
from src.merge_utils import build_room_category_map, apply_step3_merge
from src.step4_utils import load_takeoff, build_step4_outputs
from src.step5_utils import load_material_master, match_materials
from src.step6_utils import build_step6_output
from src.export_utils import build_export_workbook

APP_TITLE = "Order Processing – Steps 0–7"
TAKEOFF_DEFAULT_PATH = os.path.join("data", "ELSTON II - Takeoff.xlsx")
MATERIAL_MASTER_DEFAULT_PATH = os.path.join("data", "Material_Description.xlsx")
TRADE_COMBO_DEFAULT_PATH = os.path.join("data", "Trade_Material_Combinations.xlsx")

def init_state():
    st.session_state.setdefault("step_idx", 0)
    st.session_state.setdefault("verified", {0: False, 1: False, 2: False, 3: False, 4: False, 5: False, 6: False, 7: False})

    st.session_state.setdefault("selection_file", None)
    st.session_state.setdefault("floorplan_file", None)

    st.session_state.setdefault("step1_df", None)
    st.session_state.setdefault("step2_rooms_df", None)
    st.session_state.setdefault("step2_trans_df", None)

    st.session_state.setdefault("step3_a_df", None)
    st.session_state.setdefault("step3_b_df", None)
    st.session_state.setdefault("room_category_map_df", None)

    st.session_state.setdefault("takeoff_bytes", None)
    st.session_state.setdefault("takeoff_df", None)

    st.session_state.setdefault("step4_c_df", None)
    st.session_state.setdefault("step4_d_df", None)

    st.session_state.setdefault("material_master_bytes", None)
    st.session_state.setdefault("material_master_df", None)
    st.session_state.setdefault("step5_df", None)
    st.session_state.setdefault("trade_combo_bytes", None)
    st.session_state.setdefault("step6_df", None)
    st.session_state.setdefault("export_xlsx_bytes", None)

init_state()

def go(step: int):
    st.session_state.step_idx = step
    st.rerun()

def require_verified(step: int):
    if not st.session_state.verified.get(step, False):
        st.error(f"You must verify Step {step} before proceeding.")
        st.stop()

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)

with st.sidebar:
    st.subheader("Steps (gated)")
    labels = [
        "1. Start Here with Selection Sheet & Floorplan",
        "2. What is ILG doing?",
        "3. How does the Floor look like?",
        "4. Rooms with Installations & Transitions",
        "5. Installation Material Takeoff by Room & Trade",
        "6. Get SAP # for Materials",
        "7. Get Sundries & Labor for Trade Installation",
        "8. Get Ready to Send to SAP",
    ]
    for i, label in enumerate(labels):
        done = "✅" if st.session_state.verified.get(i) else "⬜"
        disabled = (i > 0 and not st.session_state.verified.get(i-1, False))
        if st.button(f"{done} {label}", use_container_width=True, disabled=disabled):
            go(i)

# Step 0
if st.session_state.step_idx == 0:
    st.header("Step 0 – Mandatory uploads")

    c1, c2 = st.columns(2)
    with c1:
        sel = st.file_uploader("Upload Selection Sheet (PDF/image preferred)", type=["pdf","png","jpg","jpeg"], key="u_sel")
        if sel:
            st.session_state.selection_file = {"name": sel.name, "ext": sel.name.split(".")[-1].lower(), "bytes": sel.getvalue()}

    with c2:
        fp = st.file_uploader("Upload Floorplan (PDF/image preferred)", type=["pdf","png","jpg","jpeg"], key="u_fp")
        if fp:
            st.session_state.floorplan_file = {"name": fp.name, "ext": fp.name.split(".")[-1].lower(), "bytes": fp.getvalue()}

    if st.session_state.selection_file and st.session_state.floorplan_file:
        st.success("Both required documents uploaded.")
        if st.button("Proceed to Step 1", type="primary"):
            st.session_state.verified[0] = True
            go(1)
    else:
        st.info("Upload both documents to continue.")
    st.stop()

# Step 1
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
                imgs = pdf_bytes_to_images(sel_file["bytes"]) if sel_file["ext"] == "pdf" else image_bytes_to_images(sel_file["bytes"])
                rows = extract_step1_builder_selections(imgs)
                st.session_state.step1_df = pd.DataFrame(rows, columns=["Room", "Trade", "Material Description"])
        with colB:
            if st.button("Reset table"):
                st.session_state.step1_df = pd.DataFrame(columns=["Room", "Trade", "Material Description"])

        st.session_state.step1_df = st.data_editor(st.session_state.step1_df, num_rows="dynamic", use_container_width=True, key="step1_editor")

        st.divider()
        if st.button("I have verified the Builder Selections. Move to Step 2", type="primary"):
            st.session_state.verified[1] = True
            go(2)
    st.stop()

# Step 2
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
            st.session_state.step2_trans_df = pd.DataFrame(columns=["Room","Adjoining Room","Transition needed"])

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("Run OpenAI extraction", type="primary"):
                imgs = pdf_bytes_to_images(fp_file["bytes"]) if fp_file["ext"] == "pdf" else image_bytes_to_images(fp_file["bytes"])
                rooms, transitions = extract_step2_rooms_transitions(imgs)
                st.session_state.step2_rooms_df = pd.DataFrame(rooms, columns=["Room"])
                st.session_state.step2_trans_df = pd.DataFrame(transitions, columns=["Room","Adjoining Room","Transition needed"])
        with colB:
            if st.button("Reset outputs"):
                st.session_state.step2_rooms_df = pd.DataFrame(columns=["Room"])
                st.session_state.step2_trans_df = pd.DataFrame(columns=["Room","Adjoining Room","Transition needed"])

        st.session_state.step2_rooms_df = st.data_editor(st.session_state.step2_rooms_df, num_rows="dynamic", use_container_width=True, key="step2_rooms_editor")
        st.subheader("Room | Adjoining Room | Transition needed (editable)")
        st.session_state.step2_trans_df = st.data_editor(st.session_state.step2_trans_df, num_rows="dynamic", use_container_width=True, key="step2_trans_editor")

        st.divider()
        if st.button("I have verified the Rooms. Move to Step 3", type="primary"):
            st.session_state.verified[2] = True
            go(3)
    st.stop()

# Step 3
if st.session_state.step_idx == 3:
    require_verified(2)
    st.header("Step 3 – Merge Step 1 + Step 2")

    step1 = st.session_state.step1_df.copy() if st.session_state.step1_df is not None else pd.DataFrame(columns=["Room","Trade","Material Description"])
    rooms = st.session_state.step2_rooms_df.copy() if st.session_state.step2_rooms_df is not None else pd.DataFrame(columns=["Room"])
    trans = st.session_state.step2_trans_df.copy() if st.session_state.step2_trans_df is not None else pd.DataFrame(columns=["Room","Adjoining Room","Transition needed"])

    if rooms.empty:
        st.error("Rooms list is empty. Go back to Step 2.")
        st.stop()

    st.subheader("3A. Room → Category mapping (editable)")
    if st.session_state.room_category_map_df is None or st.session_state.room_category_map_df.empty:
        st.session_state.room_category_map_df = build_room_category_map(rooms)

    st.session_state.room_category_map_df = st.data_editor(st.session_state.room_category_map_df, num_rows="dynamic", use_container_width=True, key="room_cat_map_editor")

    outA, outB, diagnostics = apply_step3_merge(step1, rooms, trans, st.session_state.room_category_map_df)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Output A:** Room (from Step 2) | Trade | Material Description")
        st.session_state.step3_a_df = st.session_state.step3_a_df if st.session_state.step3_a_df is not None else outA
        st.session_state.step3_a_df = st.data_editor(st.session_state.step3_a_df, num_rows="dynamic", use_container_width=True, key="step3_a_editor")
    with c2:
        st.markdown("**Output B:** Room | Adjoining Room | Trade | Transition needed")
        st.session_state.step3_b_df = st.session_state.step3_b_df if st.session_state.step3_b_df is not None else outB
        st.session_state.step3_b_df = st.data_editor(st.session_state.step3_b_df, num_rows="dynamic", use_container_width=True, key="step3_b_editor")

    st.divider()
    st.subheader("Diagnostics")
    st.dataframe(diagnostics, use_container_width=True)

    st.divider()
    if st.button("I have verified the Rooms & Transitions. Move to Step 4", type="primary"):
        st.session_state.verified[3] = True
        go(4)
    st.stop()

# Step 4
if st.session_state.step_idx == 4:
    require_verified(3)
    st.header("Step 4 – Cross reference Takeoff (Rooms/Trade/Gross Qty)")

    st.caption("Takeoff workbook is embedded with the app at: data/ELSTON II - Takeoff.xlsx. You can still upload a replacement for this session if needed.")
    takeoff_upload = st.file_uploader("Upload ELSTON II - Takeoff.xlsx (if not preloaded)", type=["xlsx"], key="u_takeoff")
    if takeoff_upload:
        st.session_state.takeoff_bytes = takeoff_upload.getvalue()

    try:
        st.session_state.takeoff_df = load_takeoff(TAKEOFF_DEFAULT_PATH, override_bytes=st.session_state.takeoff_bytes)
        st.success(f"Loaded takeoff rows: {len(st.session_state.takeoff_df)}")
    except Exception as e:
        st.error(f"Unable to load takeoff workbook. {e}")
        st.stop()

    if st.session_state.step3_a_df is None or st.session_state.step3_a_df.empty:
        st.error("Step 3 Output A is missing/empty.")
        st.stop()

    outC, outD, diag = build_step4_outputs(st.session_state.step3_a_df, st.session_state.takeoff_df)

    st.subheader("Output C (editable): Room | Trade | Gross Qty | UOM | Material Description")
    if st.session_state.step4_c_df is None:
        st.session_state.step4_c_df = outC
    st.session_state.step4_c_df = st.data_editor(st.session_state.step4_c_df, num_rows="dynamic", use_container_width=True, key="step4_c_editor")

    st.subheader("Output D (editable): Trade | Material Description | Gross Qty | UOM")
    if st.session_state.step4_d_df is None:
        st.session_state.step4_d_df = outD
    st.session_state.step4_d_df = st.data_editor(st.session_state.step4_d_df, num_rows="dynamic", use_container_width=True, key="step4_d_editor")

    st.subheader("Join diagnostics (unmatched Room/Trade)")
    st.dataframe(diag, use_container_width=True)

    st.divider()
    if st.button("I have verified the Quantities. Move to Step 5", type="primary"):
        st.session_state.verified[4] = True
        go(5)
    st.stop()


# Step 5
if st.session_state.step_idx == 5:
    require_verified(4)
    st.header("Step 5 – Map Material Descriptions to SAP Materials")

    st.caption("Material master is expected at: data/Material_Description.xlsx. "
               "If not embedded yet, upload it below for this session. (Later we can embed it permanently.)")

    mm_upload = st.file_uploader("Upload Material_Description.xlsx (if not embedded)", type=["xlsx"], key="u_mat_master")
    if mm_upload:
        st.session_state.material_master_bytes = mm_upload.getvalue()

    try:
        st.session_state.material_master_df = load_material_master(
            MATERIAL_MASTER_DEFAULT_PATH,
            override_bytes=st.session_state.material_master_bytes
        )
        st.success(f"Loaded material master rows: {len(st.session_state.material_master_df)}")
    except Exception as e:
        st.error(f"Unable to load material master workbook. {e}")
        st.stop()

    if st.session_state.step4_d_df is None or st.session_state.step4_d_df.empty:
        st.error("Step 4 Output D is missing/empty.")
        st.stop()

    colA, colB = st.columns([1, 1])
    with colA:
        threshold = st.slider("Confidence threshold (%)", 50, 95, 80, 1)
    with colB:
        top_n = st.slider("Options to show when below threshold", 3, 10, 5, 1)

    if st.button("Run SAP material matching", type="primary"):
        step5_df, diag = match_materials(
            output_d=st.session_state.step4_d_df,
            master_df=st.session_state.material_master_df,
            threshold=float(threshold),
            top_n=int(top_n),
        )
        st.session_state.step5_df = step5_df
        st.session_state.step5_diag = diag

    if st.session_state.get("step5_df") is None:
        st.info("Click 'Run SAP material matching' to generate Output.")
        st.stop()

    st.subheader("Output (editable): Trade | Material Description | SAP Material | SAP Material Description | Confidence %")
    edited = st.data_editor(
        st.session_state.step5_df,
        num_rows="dynamic",
        use_container_width=True,
        key="step5_editor",
    )
    st.session_state.step5_df = edited

    st.subheader("Low-confidence diagnostics (below threshold)")
    st.dataframe(st.session_state.get("step5_diag", pd.DataFrame()), use_container_width=True)

    st.divider()
    if st.button("I have verified the SAP Materials. Move to Step 6", type="primary"):
        st.session_state.verified[5] = True
        go(6)

    st.stop()


# Step 6
if st.session_state.step_idx == 6:
    require_verified(5)
    st.header("Step 6 – Sundries & Labor from Trade/Material Combinations")

    st.caption("Trade/Material combination workbook is embedded at: data/Trade_Material_Combinations.xlsx. "
               "You may upload a replacement for this session if needed.")

    combo_upload = st.file_uploader("Upload Trade_Material_Combinations.xlsx (optional override)", type=["xlsx"], key="u_trade_combo")
    if combo_upload:
        st.session_state.trade_combo_bytes = combo_upload.getvalue()

    # Decide workbook path: embedded file on disk; if override bytes, write temp to /tmp
    workbook_path = TRADE_COMBO_DEFAULT_PATH
    if st.session_state.trade_combo_bytes:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.write(st.session_state.trade_combo_bytes)
        tmp.flush()
        workbook_path = tmp.name

    if st.session_state.step4_d_df is None or st.session_state.step4_d_df.empty:
        st.error("Step 4 Output D is missing/empty.")
        st.stop()

    if st.button("Generate Sundries & Labor", type="primary"):
        st.session_state.step6_df = build_step6_output(st.session_state.step4_d_df, workbook_path)

    if st.session_state.step6_df is None:
        st.info("Click 'Generate Sundries & Labor' to create the Step 6 output.")
        st.stop()

    st.subheader("Output (editable): Trade | Material | Material Description | Qty | UOM | Type of Material")
    st.session_state.step6_df = st.data_editor(
        st.session_state.step6_df,
        num_rows="dynamic",
        use_container_width=True,
        key="step6_editor",
    )

    st.divider()
    if st.button("I have verified the Sundries & Labor. Move to Step 7", type="primary"):
        st.session_state.verified[6] = True
        go(7)

    st.stop()


# Step 7
if st.session_state.step_idx == 7:
    require_verified(6)
    st.header("Step 7 – Final Review & Export")

    st.caption("Review the finalized outputs and export the full package as an Excel workbook.")

    # Collect all key outputs (best-effort)
    dfs = {
        "Step1_BuilderSelections": st.session_state.get("step1_df"),
        "Step2_Rooms": st.session_state.get("step2_rooms_df"),
        "Step2_Transitions": st.session_state.get("step2_trans_df"),
        "Step3_OutputA_RoomTradeMat": st.session_state.get("step3_a_df"),
        "Step3_OutputB_Transitions": st.session_state.get("step3_b_df"),
        "Step4_OutputC_RoomTradeQty": st.session_state.get("step4_c_df"),
        "Step4_OutputD_TradeMatQty": st.session_state.get("step4_d_df"),
        "Step5_SAP_Mapping": st.session_state.get("step5_df"),
        "Step6_Sundries_Labor": st.session_state.get("step6_df"),
    }

    # Quick KPI summary
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Rooms", 0 if dfs["Step2_Rooms"] is None else len(dfs["Step2_Rooms"]))
    k2.metric("Output D lines", 0 if dfs["Step4_OutputD_TradeMatQty"] is None else len(dfs["Step4_OutputD_TradeMatQty"]))
    k3.metric("SAP mapped lines", 0 if dfs["Step5_SAP_Mapping"] is None else len(dfs["Step5_SAP_Mapping"]))
    k4.metric("Sundries/Labor lines", 0 if dfs["Step6_Sundries_Labor"] is None else len(dfs["Step6_Sundries_Labor"]))

    st.divider()

    st.subheader("Export")
    if st.button("Build Excel export", type="primary"):
        st.session_state.export_xlsx_bytes = build_export_workbook(dfs)
        st.success("Export workbook generated.")

    if st.session_state.export_xlsx_bytes:
        st.download_button(
            "Download Order Package (xlsx)",
            data=st.session_state.export_xlsx_bytes,
            file_name="Order_Processing_Package.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    st.divider()
    st.subheader("Spot-check views")
    with st.expander("View Output D (Trade | Material Description | Gross Qty | UOM)", expanded=True):
        if dfs["Step4_OutputD_TradeMatQty"] is None:
            st.info("Output D not found.")
        else:
            st.dataframe(dfs["Step4_OutputD_TradeMatQty"], use_container_width=True)

    with st.expander("View Step 6 (Sundries & Labor)", expanded=False):
        if dfs["Step6_Sundries_Labor"] is None:
            st.info("Step 6 output not found.")
        else:
            st.dataframe(dfs["Step6_Sundries_Labor"], use_container_width=True)

    st.divider()
    if st.button("Mark Order as Complete", type="primary"):
        st.session_state.verified[7] = True
        st.success("Order marked complete.")
    st.stop()
