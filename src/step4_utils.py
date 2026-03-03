from __future__ import annotations
import io
import re
from typing import Optional, Tuple, Dict
import pandas as pd


def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s


def _trade_key(trade: str) -> str:
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


def load_takeoff(path: str, override_bytes: Optional[bytes] = None) -> pd.DataFrame:
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

    room_col = find_col(["Room", "ROOM", "Area", "AREA"])
    trade_col = find_col(["Trade", "TRADE"])
    gross_col = find_col(["Gross Quantity", "Gross Qty", "GROSS QUANTITY", "GROSS QTY", "Gross"])
    uom_col = find_col(["UOM", "Unit", "UNIT", "Units"])

    missing = [("Room", room_col), ("Trade", trade_col), ("Gross Qty", gross_col)]
    miss = [name for name, col in missing if col is None]
    if miss:
        raise ValueError(f"Missing required columns: {', '.join(miss)}. Found: {list(df.columns)}")

    out = pd.DataFrame(
        {
            "Room": df[room_col].astype(str),
            "Trade": df[trade_col].astype(str),
            "Gross Qty": pd.to_numeric(df[gross_col], errors="coerce"),
            "UOM": df[uom_col].astype(str) if uom_col else "",
        }
    )

    out["Room_norm"] = out["Room"].map(_norm)
    out["Trade_norm"] = out["Trade"].map(_norm)
    return out


def _trade_to_material_desc(step1_df: pd.DataFrame) -> Dict[str, str]:
    """
    Build TradeKey -> Material Description mapping from Selection Sheet output (Step 1).

    Rule:
      - normalize trade into a key (CARPET/LVP/TILE/VINYL/WOOD/...)
      - pick the most frequent non-blank material description per trade (mode); fallback to first non-blank
    """
    if step1_df is None or step1_df.empty:
        return {}

    s1 = step1_df.copy()
    for c in ["Trade", "Material Description"]:
        if c not in s1.columns:
            return {}
        s1[c] = s1[c].astype(str)

    s1["TradeKey"] = s1["Trade"].map(_trade_key)
    s1["MatDesc"] = s1["Material Description"].astype(str).map(lambda x: x.strip())
    s1 = s1[s1["MatDesc"].astype(bool)]

    out: Dict[str, str] = {}
    if s1.empty:
        return out

    for tk, g in s1.groupby("TradeKey"):
        vc = g["MatDesc"].value_counts(dropna=True)
        out[tk] = str(vc.index[0]) if not vc.empty else str(g["MatDesc"].iloc[0])
    return out


def build_step4_outputs(
    step3_a_df: pd.DataFrame,
    step1_df: pd.DataFrame,
    takeoff_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Step 4 outputs:
      - Output C: Room | Trade | Gross Qty | UOM | Material Description
      - Output D: Trade | Material Description | Gross Qty | UOM

    Per requirements:
      - Gross Qty & UOM are pulled strictly from the takeoff workbook (takeoff_df).
      - Material Description is pulled from Selection Sheet (Step 1) based on Trade.
    """
    a = step3_a_df.copy()
    for col in ["Room", "Trade"]:
        if col not in a.columns:
            raise ValueError(f"Step 3 Output A missing column: {col}")
        a[col] = a[col].astype(str)

    a["Room_norm"] = a["Room"].map(_norm)
    a["Trade_norm"] = a["Trade"].map(_norm)
    a["TradeKey"] = a["Trade"].map(_trade_key)

    trade_to_desc = _trade_to_material_desc(step1_df)
    a["Material Description"] = a["TradeKey"].map(lambda k: trade_to_desc.get(k, "")).astype(str)

    merged = a.merge(
        takeoff_df[["Room_norm", "Trade_norm", "Gross Qty", "UOM"]],
        on=["Room_norm", "Trade_norm"],
        how="left",
    )

    outC = merged[["Room", "Trade", "Gross Qty", "UOM", "Material Description"]].copy()

    outD = (
        outC.groupby(["Trade", "Material Description", "UOM"], dropna=False, as_index=False)["Gross Qty"]
        .sum()
        .sort_values(["Trade", "Material Description"])
    )

    return outC, outD
