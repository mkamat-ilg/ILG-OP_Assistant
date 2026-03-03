import os
import streamlit as st
import pandas as pd

from src.pdf_utils import pdf_bytes_to_images, image_bytes_to_images, render_doc_viewer, render_doc_viewer_container
from src.openai_client import extract_step1_builder_selections, extract_step2_rooms_transitions
from src.merge_utils import apply_step3_merge_v2
from src.step4_utils import load_takeoff, build_step4_outputs
from src.step5_utils import load_material_master, match_materials
from src.step6_utils import build_step6_output
from src.export_utils import build_export_workbook

# --------------------------------------------------
# Canonical Room → Trade Mapping (Normalization Safe)
# --------------------------------------------------

def _norm_room(s: str) -> str:
    if s is None:
        return ""
    return " ".join(str(s).strip().upper().split())


ROOM_TRADE_MAP = {
    "Great Room": "LVP",
    "Kitchen": "LVP",
    "Pantry": "LVP",
    "Storage": "Non Flooring",
    "Garage": "Non Flooring",
    "Foyer": "Non Flooring",
    "Entry": "LVP",
    "Powder": "LVP",
    "Loft": "LVP",
    "Laundry": "LVP",
    "Bath 1": "LVP",
    "Bath 2": "LVP",
    "Bedroom 1": "Carpet",
    "Bedroom 2": "Carpet",
    "Bedroom 3": "Carpet",
    "Bedroom 4": "Carpet",
    "BR1 WIC": "Carpet",
}

ROOM_TRADE_MAP_NORM = {_norm_room(k): v for k, v in ROOM_TRADE_MAP.items()}

APP_TITLE = "Order Processing Assistant"
TAKEOFF_DEFAULT_PATH = os.path.join("data", "ELSTON II - Takeoff.xlsx")
MATERIAL_MASTER_DEFAULT_PATH = os.path.join("data", "Material_Description.xlsx")
TRADE_COMBO_DEFAULT_PATH = os.path.join("data", "Trade_Material_Combinations.xlsx")


START_SELECTION_PATH = os.path.join("data", "1-SelectionSheet.pdf")
START_FLOORPLAN_PATH = os.path.join("data", "1-FloorPlan.pdf")


def _load_local_file(path: str) -> dict:
    with open(path, "rb") as f:
        b = f.read()
    name = os.path.basename(path)
    ext = name.split(".")[-1].lower()
    return {"name": name, "ext": ext, "bytes": b}

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
        "Start Here with Selection Sheet & Floorplan",
        "What is ILG doing?",
        "How does the Floor look like?",
        "Rooms with Installations & Transitions",
        "Installation Material Takeoff by Room & Trade",
        "Get SAP # for Materials",
        "Get Sundries & Labor for Trade Installation",
        "Get Ready to Send to SAP",
    ]
    for i, label in enumerate(labels):
        done = "✅" if st.session_state.verified.get(i) else "⬜"
        disabled = (i > 0 and not st.session_state.verified.get(i-1, False))
        if st.button(f"{done} {label}", use_container_width=True, disabled=disabled):
            go(i)

# Step 0
if st.session_state.step_idx == 0:
    st.header("Please Upload Selection Sheet and Floorplan to get started")

    st.subheader("Start options")
    start_mode = st.radio(
        "Choose how to provide the starting documents",
        ["Use files in the app data folder", "Upload from desktop"],
        horizontal=True,
        key="start_mode",
    )

    data_sel_exists = os.path.exists(START_SELECTION_PATH)
    data_fp_exists = os.path.exists(START_FLOORPLAN_PATH)

    if start_mode == "Use files in the app data folder":
        c_status1, c_status2 = st.columns(2)
        with c_status1:
            st.write(f"Selection Sheet: `{START_SELECTION_PATH}`")
            st.write("✅ Found" if data_sel_exists else "❌ Not found")
        with c_status2:
            st.write(f"Floorplan: `{START_FLOORPLAN_PATH}`")
            st.write("✅ Found" if data_fp_exists else "❌ Not found")

        if st.button(
            "Use /data folder files",
            type="primary",
            disabled=not (data_sel_exists and data_fp_exists),
            help="Loads 1-SelectionSheet.pdf and 1-FloorPlan.pdf from the app's data folder.",
        ):
            st.session_state.selection_file = _load_local_file(START_SELECTION_PATH)
            st.session_state.floorplan_file = _load_local_file(START_FLOORPLAN_PATH)
            st.success("Loaded both documents from the data folder.")

    st.divider()
    st.caption("Desktop uploads are always available (you can upload to override what's currently loaded).")

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

    st.divider()
    loaded1 = st.session_state.selection_file["name"] if st.session_state.selection_file else "—"
    loaded2 = st.session_state.floorplan_file["name"] if st.session_state.floorplan_file else "—"
    st.write(f"**Loaded Selection Sheet:** {loaded1}")
    st.write(f"**Loaded Floorplan:** {loaded2}")

    if st.session_state.selection_file and st.session_state.floorplan_file:
        st.success("Both required documents are loaded.")
        if st.button("Proceed to Step 1", type="primary"):
            st.session_state.verified[0] = True
            go(1)
    else:
        st.info("Load both documents (from /data or desktop upload) to continue.")
    st.stop()


# Step 1
if st.session_state.step_idx == 1:
    require_verified(0)
    st.header("Step 1 – Let's get the Flooring Work for ILG")

    sel_file = st.session_state.selection_file
    left, right = st.columns([1, 1])

    with right:
        st.subheader("Selection Sheet (scroll + zoom for verification)")
        render_doc_viewer_container(sel_file, key_prefix="sel_view", height_px=720)

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
    st.header("Step 2 – Let's get the Rooms & Transitions")

    fp_file = st.session_state.floorplan_file
    left, right = st.columns([1, 1])

    with right:
        st.subheader("Floorplan (scroll + zoom for verification)")
        render_doc_viewer_container(fp_file, key_prefix="fp_view", height_px=720)

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

        st.session_state.step2_rooms_df = st.data_editor(
            st.session_state.step2_rooms_df,
            num_rows="dynamic",
            use_container_width=True,
            key="step2_rooms_editor",
        )

        # Keep transitions aligned to the Rooms list (authoritative).
        rooms_list = [str(r).strip() for r in st.session_state.step2_rooms_df.get("Room", pd.Series(dtype=str)).tolist()]
        rooms_list = [r for r in rooms_list if r]

        if rooms_list:
            # Drop transitions referencing removed rooms.
            tdf = st.session_state.step2_trans_df.copy()
            for c in ["Room", "Adjoining Room", "Transition needed"]:
                if c in tdf.columns:
                    tdf[c] = tdf[c].astype(str)
            if not tdf.empty:
                tdf = tdf[tdf["Room"].isin(rooms_list) & tdf["Adjoining Room"].isin(rooms_list)].copy()
            st.session_state.step2_trans_df = tdf

        st.subheader("Room | Adjoining Room | Transition needed (editable)")
        st.session_state.step2_trans_df = st.data_editor(
            st.session_state.step2_trans_df,
            num_rows="dynamic",
            use_container_width=True,
            key="step2_trans_editor",
            column_config={
                "Room": st.column_config.SelectboxColumn("Room", options=rooms_list or []),
                "Adjoining Room": st.column_config.SelectboxColumn("Adjoining Room", options=rooms_list or []),
            },
        )

        st.divider()
        if st.button("I have verified the Rooms. Move to Step 3", type="primary"):
            st.session_state.verified[2] = True
            go(3)
    st.stop()

# Step 3
if st.session_state.step_idx == 3:
    require_verified(2)
    st.header("Step 3 – Consolidated Summary of Rooms, Trades & Transitions required")

    step1 = st.session_state.get("step1_df")
    step1 = step1.copy() if step1 is not None else pd.DataFrame(columns=["Room", "Trade", "Material Description"])

    rooms = st.session_state.get("step2_rooms_df")
    rooms = rooms.copy() if rooms is not None else pd.DataFrame(columns=["Room"])

    trans = st.session_state.get("step2_trans_df")
    trans = trans.copy() if trans is not None else pd.DataFrame(columns=["Room", "Adjoining Room", "Transition needed"])

    if rooms.empty:
        st.error("Rooms list is empty. Go back to Step 2.")
        st.stop()

    # Initial build (3A removed).
    outA_init, _ = apply_step3_merge_v2(step1, rooms, trans)

    # --------------------------------------------------
    # Enforce canonical Room → Trade mapping (normalization-safe)
    # --------------------------------------------------
    if not outA_init.empty and "Room" in outA_init.columns:
        outA_init["Room_norm"] = outA_init["Room"].map(_norm_room)
        outA_init["Trade"] = outA_init.apply(
            lambda r: ROOM_TRADE_MAP_NORM.get(r["Room_norm"], r.get("Trade", "")),
            axis=1,
        )
        outA_init.drop(columns=["Room_norm"], inplace=True)

    # Remove Non Flooring rows from installation workflow (recommended)
    if "Trade" in outA_init.columns:
        outA_init = outA_init[~outA_init["Trade"].astype(str).str.strip().str.upper().eq("NON FLOORING")].reset_index(drop=True)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Output A:** Room (from Step 2) | Trade | Material Description")

        step3_a_df = st.session_state.get("step3_a_df")
        if not isinstance(step3_a_df, pd.DataFrame) or step3_a_df.empty:
            st.session_state["step3_a_df"] = outA_init

        def _on_step3_a_change() -> None:
            # Ensure dependent computations (Output B) see the latest edits in the same rerun
            st.session_state["step3_a_df"] = st.session_state.get("step3_a_editor", st.session_state.get("step3_a_df"))

        edited_a = st.data_editor(
            st.session_state.get("step3_a_df"),
            num_rows="dynamic",
            use_container_width=True,
            key="step3_a_editor",
            on_change=_on_step3_a_change,
            column_config={
                "Trade": st.column_config.SelectboxColumn(
                    "Trade",
                    options=["Carpet", "Tile", "LVP", "Vinyl", "Wood", "Non Flooring"],
                    required=True,
                )
            },
        )
        st.session_state["step3_a_df"] = edited_a

    # Helpers
    def _norm_room(s: str) -> str:
        import re as _re
        s = "" if s is None else str(s)
        s = s.strip().upper()
        s = _re.sub(r"\s+", " ", s)
        return s

    def _trade_key(trade: str) -> str:
        t = _norm_room(trade)
        if "CARPET" in t:
            return "CARPET"
        if "LVP" in t or "EVP" in t:
            return "LVP"
        if "TILE" in t:
            return "TILE"
        if "VINYL" in t:
            return "VINYL"
        if "WOOD" in t:
            return "WOOD"
        return t

    # Compute Output B from Output A + Step 2 adjacency
    a_df_src = st.session_state.get("step3_a_df")
    a_df = a_df_src.copy() if isinstance(a_df_src, pd.DataFrame) else pd.DataFrame(columns=["Room", "Trade", "Material Description"])

    trade_map = {_norm_room(r): _trade_key(t) for r, t in zip(a_df.get("Room", []), a_df.get("Trade", []))}

    if trans.empty:
        outB_full = pd.DataFrame(
            columns=["Room", "Adjoining Room", "Trade In Room", "Trade In Adjoining Room", "Transition Needed"]
        )
    else:
        outB_rows = []
        for _, tr in trans.iterrows():
            room = str(tr.get("Room", ""))
            adj = str(tr.get("Adjoining Room", ""))

            tk_room = trade_map.get(_norm_room(room), "")
            tk_adj = trade_map.get(_norm_room(adj), "")

            tk_room_disp = tk_room.title() if tk_room and tk_room != "LVP" else ("LVP" if tk_room == "LVP" else "")
            tk_adj_disp = tk_adj.title() if tk_adj and tk_adj != "LVP" else ("LVP" if tk_adj == "LVP" else "")

            need = "Yes" if _norm_room(tk_room_disp) != _norm_room(tk_adj_disp) else "No"

            outB_rows.append(
                {
                    "Room": room,
                    "Adjoining Room": adj,
                    "Trade In Room": tk_room_disp,
                    "Trade In Adjoining Room": tk_adj_disp,
                    "Transition Needed": need,
                }
            )
        outB_full = pd.DataFrame(outB_rows)

    # Store full computed Output B in state for downstream steps
    st.session_state["step3_b_df"] = outB_full

    with c2:
        st.markdown("**Output B:** Room | Adjoining Room | Trade In Room | Trade In Adjoining Room | Transition Needed")

        hide_no = st.checkbox("Hide rows where Transition Needed is No", value=True, key="step3_hide_no")

        display_df = outB_full.copy()
        if hide_no and not display_df.empty:
            display_df = display_df[
                ~display_df["Transition Needed"].astype(str).str.strip().str.upper().eq("NO")
            ].reset_index(drop=True)

        st.data_editor(
            display_df,
            num_rows="dynamic",
            use_container_width=True,
            key="step3_b_editor",
            disabled=["Trade In Room", "Trade In Adjoining Room", "Transition Needed"],
        )

    st.divider()
    if st.button("I have verified the Rooms & Transitions. Move to Step 4", type="primary"):
        st.session_state.verified[3] = True
        go(4)
    st.stop()

# Step 4
if st.session_state.step_idx == 4:
    require_verified(3)
    st.header("Step 4 – Let's get the Quantity to be ordered for Installation Materials as per TakeOff")

    st.caption("Gross Qty and UOM are loaded strictly from the embedded takeoff workbook: data/ELSTON II - Takeoff.xlsx")

    try:
        st.session_state.takeoff_df = load_takeoff(TAKEOFF_DEFAULT_PATH, override_bytes=None)
        st.success(f"Loaded takeoff rows: {len(st.session_state.takeoff_df)}")
    except Exception as e:
        st.error(f"Unable to load takeoff workbook. {e}")
        st.stop()

    if st.session_state.step3_a_df is None or st.session_state.step3_a_df.empty:
        st.error("Step 3 Output A is missing/empty.")
        st.stop()

    if st.session_state.step1_df is None or st.session_state.step1_df.empty:
        st.error("Step 1 output is missing/empty. Material Description must come from Selection Sheet.")
        st.stop()

    outC, outD = build_step4_outputs(
        step3_a_df=st.session_state.step3_a_df,
        step1_df=st.session_state.step1_df,
        takeoff_df=st.session_state.takeoff_df,
    )

    st.subheader("Output C (editable): Room | Trade | Gross Qty | UOM | Material Description")
    if st.session_state.step4_c_df is None:
        st.session_state.step4_c_df = outC
    st.session_state.step4_c_df = st.data_editor(
        st.session_state.step4_c_df, num_rows="dynamic", use_container_width=True, key="step4_c_editor"
    )

    st.subheader("Output D (editable): Trade | Material Description | Gross Qty | UOM")
    if st.session_state.step4_d_df is None:
        st.session_state.step4_d_df = outD
    st.session_state.step4_d_df = st.data_editor(
        st.session_state.step4_d_df, num_rows="dynamic", use_container_width=True, key="step4_d_editor"
    )

    st.divider()
    if st.button("I have verified the Quantities. Move to Step 5", type="primary"):
        st.session_state.verified[4] = True
        go(5)
    st.stop()


# Step 5
if st.session_state.step_idx == 5:
    require_verified(4)
    st.header("Step 5 – Let's identify the SAP Materials")

    st.caption("Material master is embedded at: data/Material_Description.xlsx")

    try:
        st.session_state.material_master_df = load_material_master(MATERIAL_MASTER_DEFAULT_PATH, override_bytes=None)
        st.success(f"Loaded material master rows: {len(st.session_state.material_master_df)}")
    except Exception as e:
        st.error(f"Unable to load material master workbook. {e}")
        st.stop()

    if st.session_state.step4_d_df is None or st.session_state.step4_d_df.empty:
        st.error("Step 4 Output D is missing/empty.")
        st.stop()

    if st.button("Run SAP material matching", type="primary"):
        step5_df = match_materials(
            output_d=st.session_state.step4_d_df,
            master_df=st.session_state.material_master_df,
        )
        st.session_state.step5_df = step5_df

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

    st.divider()
    if st.button("I have verified the SAP Materials. Move to Step 6", type="primary"):
        st.session_state.verified[5] = True
        go(6)

    st.stop()


# Step 6
if st.session_state.step_idx == 6:
    require_verified(5)
    st.header("Step 6 – Let's get the Sundries & Labor for the Flooring Work")

    st.caption("Trade/Material combination workbook is embedded at: data/Trade_Material_Combinations.xlsx")

    if st.session_state.step4_d_df is None or st.session_state.step4_d_df.empty:
        st.error("Step 4 Output D is missing/empty.")
        st.stop()

    if st.session_state.step5_df is None or st.session_state.step5_df.empty:
        st.error("Step 5 output is missing/empty. Step 6 requires SAP Material mapping.")
        st.stop()

    if st.button("Generate Sundries & Labor", type="primary"):
        st.session_state.step6_df = build_step6_output(
            output_d=st.session_state.step4_d_df,
            step5_df=st.session_state.step5_df,
            workbook_path=TRADE_COMBO_DEFAULT_PATH,
        )

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
    st.header("Step 7 – Final Review to Send to SAP")

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
