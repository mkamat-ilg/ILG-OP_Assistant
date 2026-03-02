from __future__ import annotations
import io
import re
from typing import Optional, Tuple
import pandas as pd

def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s

def load_takeoff(path: str, override_bytes: Optional[bytes] = None) -> pd.DataFrame:
    if override_bytes:
        df = pd.read_excel(io.BytesIO(override_bytes))
    else:
        df = pd.read_excel(path)

    # normalize column names
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]

    def find_col(candidates):
        for cand in candidates:
            for c in df.columns:
                if str(c).strip().upper() == cand.upper():
                    return c
        return None

    room_col = find_col(["Room", "ROOM", "Area", "AREA"])
    trade_col = find_col(["Trade", "TRADE"])
    gross_col = find_col(["Gross Quantity", "Gross Qty", "GROSS QUANTITY", "GROSS QTY", "Gross"])
    uom_col = find_col(["UOM", "Unit", "UNIT", "Units"])

    missing = [("Room", room_col), ("Trade", trade_col), ("Gross Qty", gross_col)]
    miss = [name for name, col in missing if col is None]
    if miss:
        raise ValueError(f"Missing required columns: {', '.join(miss)}. Found: {list(df.columns)}")

    out = pd.DataFrame({
        "Room": df[room_col].astype(str),
        "Trade": df[trade_col].astype(str),
        "Gross Qty": pd.to_numeric(df[gross_col], errors="coerce"),
        "UOM": df[uom_col].astype(str) if uom_col else "",
    })

    out["Room_norm"] = out["Room"].map(_norm)
    out["Trade_norm"] = out["Trade"].map(_norm)
    return out

def build_step4_outputs(step3_a_df: pd.DataFrame, takeoff_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    a = step3_a_df.copy()
    for col in ["Room","Trade","Material Description"]:
        if col not in a.columns:
            raise ValueError(f"Step 3 Output A missing column: {col}")
        a[col] = a[col].astype(str)

    a["Room_norm"] = a["Room"].map(_norm)
    a["Trade_norm"] = a["Trade"].map(_norm)

    merged = a.merge(
        takeoff_df[["Room_norm","Trade_norm","Gross Qty","UOM"]],
        on=["Room_norm","Trade_norm"],
        how="left",
        indicator=True
    )

    outC = merged[["Room","Trade","Gross Qty","UOM","Material Description"]].copy()
    diag = merged[merged["_merge"] != "both"][["Room","Trade","Material Description","_merge"]].copy()
    diag.rename(columns={"_merge": "Join Status"}, inplace=True)

    outD = (
        outC.groupby(["Trade","Material Description","UOM"], dropna=False, as_index=False)["Gross Qty"]
        .sum()
        .sort_values(["Trade","Material Description"])
    )

    return outC, outD, diag
