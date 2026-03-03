from __future__ import annotations
import re
import pandas as pd
from typing import Dict, List

from src.trade_combos import generate_associated_lines


def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


def trade_to_key(trade: str) -> str:
    t = _norm(trade)
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


def build_step6_output(output_d: pd.DataFrame, step5_df: pd.DataFrame, workbook_path: str) -> pd.DataFrame:
    """
    Build sundries/labor lines by trade for each Step 4 Output D row, using the SAP Material
    identified in Step 5 as the "installation material" line.

    Inputs:
      output_d: Trade | Material Description | Gross Qty | UOM
      step5_df: Trade | Material Description | SAP Material | SAP Material Description | Confidence %
    """
    required_d = ["Trade", "Material Description", "Gross Qty", "UOM"]
    for c in required_d:
        if c not in output_d.columns:
            raise ValueError(f"Output D missing column: {c}")

    required_5 = ["Trade", "Material Description", "SAP Material", "SAP Material Description"]
    for c in required_5:
        if c not in step5_df.columns:
            raise ValueError(f"Step 5 output missing column: {c}")

    d = output_d.copy()
    s5 = step5_df.copy()

    # Normalize join keys
    d["Trade_norm"] = d["Trade"].map(_norm)
    d["MatDesc_norm"] = d["Material Description"].map(_norm)

    s5["Trade_norm"] = s5["Trade"].map(_norm)
    s5["MatDesc_norm"] = s5["Material Description"].map(_norm)

    merged = d.merge(
        s5[["Trade_norm", "MatDesc_norm", "SAP Material", "SAP Material Description"]],
        on=["Trade_norm", "MatDesc_norm"],
        how="left",
    )

    rows: List[Dict] = []
    for _, r in merged.iterrows():
        trade = str(r["Trade"])
        trade_key = trade_to_key(trade)

        gross_qty = float(r["Gross Qty"]) if str(r["Gross Qty"]).strip() != "" else 0.0
        uom = str(r["UOM"])

        sap_mat = str(r.get("SAP Material", "") or "").strip()
        sap_desc = str(r.get("SAP Material Description", "") or "").strip()

        # If Step 5 is blank (manual override not done yet), keep a visible placeholder.
        if not sap_mat:
            sap_mat = "Installation Material"
        if not sap_desc:
            sap_desc = str(r.get("Material Description", "") or "")

        lines = generate_associated_lines(
            workbook_path=workbook_path,
            trade_key=trade_key,
            installation_gross_qty=gross_qty,
            installation_uom=uom,
            installation_sap_material=sap_mat,
            installation_sap_description=sap_desc,
        )
        for ln in lines:
            rows.append(
                {
                    "Trade": ln.trade,
                    "Material": ln.material,
                    "Material Description": ln.material_desc,
                    "Qty": ln.qty,
                    "UOM": ln.uom,
                    "Type of Material": ln.material_type,
                }
            )

    return pd.DataFrame(rows)
