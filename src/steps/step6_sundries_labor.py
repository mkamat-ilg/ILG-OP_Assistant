import streamlit as st
import pandas as pd
from src.trade_combos import generate_associated_lines

WORKBOOK_PATH = "data/Trade_Material_Combinations.xlsx"

def render_step6():
    st.header("Step 6 – Sundries & Labor")

    d_df = st.session_state.get("step4_d_df")
    if d_df is None or d_df.empty:
        st.warning("Step 4 Output D is missing. Complete Step 4 first.")
        return

    st.info("Using Output D (Trade + Material Description + Gross Qty + UOM) to compute associated materials/labor.")

    if st.button("Generate Step 6 Output", type="primary"):
        out_rows = []
        for _, row in d_df.iterrows():
            trade = str(row["Trade"]).strip().upper()
            mat_desc = str(row["Material Description"]).strip()
            gross_qty = float(row["Gross Qty"])
            uom = str(row["UOM"]).strip()

            # map your trade naming to workbook tabs
            # Carpet / LVP / Tile are separate per your instruction
            if "CARPET" in trade:
                trade_key = "CARPET"
            elif "LVP" in trade or "EVP" in trade:
                trade_key = "LVP"
            elif "TILE" in trade:
                trade_key = "TILE"
            else:
                # default: try by exact
                trade_key = trade

            lines = generate_associated_lines(
                workbook_path=WORKBOOK_PATH,
                trade=trade_key,
                installation_material_desc=mat_desc,
                gross_qty=gross_qty,
                gross_uom=uom,
            )
            for ln in lines:
                out_rows.append({
                    "Trade": ln.trade,
                    "Material": ln.sap_material,
                    "Material Description": ln.material_desc,
                    "Qty": ln.qty,
                    "UOM": ln.uom,
                    "Type of Material": ln.material_type,
                })

        st.session_state["step6_df"] = pd.DataFrame(out_rows)

    df = st.session_state.get("step6_df")
    if df is not None and not df.empty:
        left, right = st.columns([1, 1])

        with left:
            st.subheader("Editable Output")
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="step6_editor")
            st.session_state["step6_df"] = edited

            verified = st.button("I have verified the Sundries & Labor. Move to Step 7", type="primary")
            if verified:
                st.session_state["verified"][6] = True
                st.session_state["step_idx"] = 7  # Step 7 placeholder in your next iteration

        with right:
            st.subheader("Reference")
            st.caption("If you want, we can also display the matching trade tab as a table for audit.")
            st.dataframe(df.head(50), use_container_width=True)
