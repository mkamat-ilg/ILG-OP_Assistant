from __future__ import annotations
import re
import pandas as pd
from typing import Dict, Tuple, List
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
    return t

def build_step6_output(output_d: pd.DataFrame, workbook_path: str) -> pd.DataFrame:
    required = ["Trade", "Material Description", "Gross Qty", "UOM"]
    for c in required:
        if c not in output_d.columns:
            raise ValueError(f"Output D missing column: {c}")

    rows: List[Dict] = []
    for _, r in output_d.iterrows():
        trade = str(r["Trade"])
        trade_key = trade_to_key(trade)
        mat_desc = str(r["Material Description"])
        gross_qty = float(r["Gross Qty"]) if str(r["Gross Qty"]).strip() != "" else 0.0
        uom = str(r["UOM"])

        lines = generate_associated_lines(
            workbook_path=workbook_path,
            trade_key=trade_key,
            installation_material_desc=mat_desc,
            gross_qty=gross_qty,
            gross_uom=uom,
        )
        for ln in lines:
            rows.append({
                "Trade": ln.trade,
                "Material": ln.material,
                "Material Description": ln.material_desc,
                "Qty": ln.qty,
                "UOM": ln.uom,
                "Type of Material": ln.material_type,
            })
    return pd.DataFrame(rows)
