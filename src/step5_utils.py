from __future__ import annotations
import io
import re
from typing import Optional, List, Dict

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
    Returns:
      SAP Material | SAP Material Description | Desc_norm
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
    desc_col = find_col(
        [
            "Material Description",
            "MATERIAL DESCRIPTION",
            "SAP Material Description",
            "SAP MATERIAL DESCRIPTION",
            "Description",
            "DESCRIPTION",
        ]
    )

    missing = [("Material", mat_col), ("Material Description", desc_col)]
    miss = [name for name, col in missing if col is None]
    if miss:
        raise ValueError(f"Missing required columns: {', '.join(miss)}. Found: {list(df.columns)}")

    out = pd.DataFrame(
        {
            "SAP Material": df[mat_col].astype(str),
            "SAP Material Description": df[desc_col].astype(str),
        }
    )
    out["Desc_norm"] = out["SAP Material Description"].map(_norm)
    out = out[out["Desc_norm"].astype(bool)].drop_duplicates(subset=["SAP Material", "Desc_norm"])
    return out.reset_index(drop=True)


def match_materials(
    output_d: pd.DataFrame,
    master_df: pd.DataFrame,
    threshold: float = 80.0,
    top_n: int = 5,
) -> pd.DataFrame:
    """
    Matches each (Trade, Material Description) in Output D to the material master.

    UI requirements:
      - No user-tunable threshold/top-N.
      - No "options" column output.

    Returns dataframe with:
      Trade | Material Description | SAP Material | SAP Material Description | Confidence %
    """
    d = output_d.copy()
    required = ["Trade", "Material Description"]
    for col in required:
        if col not in d.columns:
            raise ValueError(f"Output D missing column: {col}")
        d[col] = d[col].astype(str)

    choices = master_df["SAP Material Description"].tolist()
    desc_to_idx: Dict[str, int] = {}
    for i, desc in enumerate(choices):
        if desc not in desc_to_idx:
            desc_to_idx[desc] = i

    out_rows: List[Dict] = []

    for _, row in d.iterrows():
        trade = str(row["Trade"])
        md = str(row["Material Description"])
        md_norm = _norm(md)

        if not md_norm:
            out_rows.append(
                {
                    "Trade": trade,
                    "Material Description": md,
                    "SAP Material": "",
                    "SAP Material Description": "",
                    "Confidence %": 0.0,
                }
            )
            continue

        matches = process.extract(md, choices, scorer=fuzz.WRatio, limit=max(1, int(top_n)))
        best_choice, best_score, _ = matches[0]

        idx = desc_to_idx.get(best_choice)
        sap_mat = master_df.loc[idx, "SAP Material"] if idx is not None else ""
        sap_desc = master_df.loc[idx, "SAP Material Description"] if idx is not None else best_choice

        out_rows.append(
            {
                "Trade": trade,
                "Material Description": md,
                "SAP Material": str(sap_mat),
                "SAP Material Description": str(sap_desc),
                "Confidence %": float(best_score),
            }
        )

    out = pd.DataFrame(out_rows).sort_values(["Trade", "Material Description"]).reset_index(drop=True)
    return out
