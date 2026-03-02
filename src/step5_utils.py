from __future__ import annotations
import io
import re
from typing import Optional, List, Dict, Tuple

import pandas as pd
from rapidfuzz import process, fuzz

def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s

def load_material_master(path: str, override_bytes: Optional[bytes] = None) -> pd.DataFrame:
    """
    Loads Material_Description.xlsx (or uploaded override).
    Expected columns (case-insensitive variants):
      - Material
      - Material Description
    """
    if override_bytes:
        df = pd.read_excel(io.BytesIO(override_bytes))
    else:
        df = pd.read_excel(path)

    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]

    def find_col(candidates):
        for cand in candidates:
            for c in df.columns:
                if str(c).strip().upper() == cand.upper():
                    return c
        return None

    mat_col = find_col(["Material", "MATERIAL", "SAP Material", "SAP MATERIAL"])
    desc_col = find_col(["Material Description", "MATERIAL DESCRIPTION", "SAP Material Description", "SAP MATERIAL DESCRIPTION", "Description", "DESCRIPTION"])

    missing = [("Material", mat_col), ("Material Description", desc_col)]
    miss = [name for name, col in missing if col is None]
    if miss:
        raise ValueError(f"Missing required columns: {', '.join(miss)}. Found: {list(df.columns)}")

    out = pd.DataFrame({
        "SAP Material": df[mat_col].astype(str),
        "SAP Material Description": df[desc_col].astype(str),
    })
    out["Desc_norm"] = out["SAP Material Description"].map(_norm)
    # Drop blanks
    out = out[out["Desc_norm"].astype(bool)].drop_duplicates(subset=["SAP Material","Desc_norm"])
    return out.reset_index(drop=True)

def match_materials(
    output_d: pd.DataFrame,
    master_df: pd.DataFrame,
    threshold: float = 80.0,
    top_n: int = 5
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    For each row in Output D:
      Trade | Material Description | Gross Qty | UOM
    match Material Description to master descriptions.
    Returns:
      step5_df with required columns + Options
      diagnostics_df for low-confidence rows
    """
    d = output_d.copy()
    required = ["Trade", "Material Description", "Gross Qty", "UOM"]
    for col in required:
        if col not in d.columns:
            raise ValueError(f"Output D missing column: {col}")
        d[col] = d[col].astype(str) if col in ["Trade","Material Description","UOM"] else d[col]

    choices = master_df["SAP Material Description"].tolist()
    # Map from choice string to row indices for lookup (handle duplicates by first match)
    desc_to_idx = {}
    for i, desc in enumerate(choices):
        if desc not in desc_to_idx:
            desc_to_idx[desc] = i

    out_rows: List[Dict] = []
    low_rows: List[Dict] = []

    for _, row in d.iterrows():
        trade = str(row["Trade"])
        md = str(row["Material Description"])
        md_norm = _norm(md)

        if not md_norm:
            out_rows.append({
                "Trade": trade,
                "Material Description": md,
                "SAP Material": "",
                "SAP Material Description": "",
                "Confidence %": 0.0,
                "Options (if <80%)": "[]",
            })
            low_rows.append({"Trade": trade, "Material Description": md, "Reason": "Blank material description"})
            continue

        matches = process.extract(
            md,
            choices,
            scorer=fuzz.WRatio,
            limit=top_n
        )

        # matches: list of (choice, score, idx)
        best_choice, best_score, _ = matches[0]
        idx = desc_to_idx.get(best_choice)
        sap_mat = master_df.loc[idx, "SAP Material"] if idx is not None else ""
        sap_desc = master_df.loc[idx, "SAP Material Description"] if idx is not None else best_choice

        options = []
        for choice, score, _ in matches:
            j = desc_to_idx.get(choice)
            options.append({
                "SAP Material": master_df.loc[j, "SAP Material"] if j is not None else "",
                "SAP Material Description": choice,
                "Confidence %": float(score),
            })

        out_row = {
            "Trade": trade,
            "Material Description": md,
            "SAP Material": str(sap_mat),
            "SAP Material Description": str(sap_desc),
            "Confidence %": float(best_score),
            "Options (if <80%)": options if float(best_score) < threshold else [],
        }
        out_rows.append(out_row)

        if float(best_score) < threshold:
            low_rows.append({
                "Trade": trade,
                "Material Description": md,
                "Best Match": str(sap_desc),
                "Confidence %": float(best_score),
            })

    step5_df = pd.DataFrame(out_rows)
    diagnostics = pd.DataFrame(low_rows)
    return step5_df, diagnostics
