
from __future__ import annotations
import re
from typing import Dict, Tuple, List
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
    return t

def apply_step3_merge_v2(
    step1_df: pd.DataFrame,
    rooms_df: pd.DataFrame,
    transitions_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:

    s1 = step1_df.copy() if step1_df is not None else pd.DataFrame(columns=["Room", "Trade", "Material Description"])
    rooms = rooms_df.copy() if rooms_df is not None else pd.DataFrame(columns=["Room"])
    trans = transitions_df.copy() if transitions_df is not None else pd.DataFrame(columns=["Room", "Adjoining Room", "Transition needed"])

    for df, col in [
        (s1, "Room"),
        (s1, "Trade"),
        (s1, "Material Description"),
        (rooms, "Room"),
        (trans, "Room"),
        (trans, "Adjoining Room"),
        (trans, "Transition needed"),
    ]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    if rooms.empty:
        return (
            pd.DataFrame(columns=["Room", "Trade", "Material Description"]),
            pd.DataFrame(columns=["Room", "Adjoining Room", "Trade In Room", "Trade In Adjoining Room", "Transition Needed"]),
        )

    # Determine allowed trades from Step 1
    allowed_trades: List[str] = []
    for t in s1.get("Trade", pd.Series(dtype=str)).tolist():
        k = _trade_key(t)
        if k and k not in allowed_trades:
            allowed_trades.append(k)
    if not allowed_trades:
        allowed_trades = ["CARPET", "LVP", "TILE"]

    # Build room -> trade map (first occurrence rule)
    room_trade_map: Dict[str, Tuple[str, str]] = {}
    for _, r in s1.iterrows():
        rn = _norm(r.get("Room", ""))
        tk = _trade_key(r.get("Trade", ""))
        md = str(r.get("Material Description", ""))
        if rn and tk and rn not in room_trade_map:
            room_trade_map[rn] = (tk, md)

    # Output A (1 trade per room)
    outA_rows = []
    for _, rr in rooms.iterrows():
        rn = _norm(rr["Room"])
        if rn in room_trade_map:
            tk, md = room_trade_map[rn]
        else:
            tk = allowed_trades[0]
            md = ""
        outA_rows.append({
            "Room": rr["Room"],
            "Trade": tk.title() if tk != "LVP" else "LVP",
            "Material Description": md,
        })

    outA = pd.DataFrame(outA_rows)

    # Build trade lookup from Output A
    trade_lookup = {
        _norm(r): _trade_key(t)
        for r, t in zip(outA["Room"].tolist(), outA["Trade"].tolist())
    }

    # Output B with new required structure
    outB_rows = []
    for _, tr in trans.iterrows():
        room = str(tr.get("Room", ""))
        adj = str(tr.get("Adjoining Room", ""))
        transition_val = str(tr.get("Transition needed", ""))

        trade_room = trade_lookup.get(_norm(room), allowed_trades[0])
        trade_adj = trade_lookup.get(_norm(adj), allowed_trades[0])

        outB_rows.append({
            "Room": room,
            "Adjoining Room": adj,
            "Trade In Room": trade_room.title() if trade_room != "LVP" else "LVP",
            "Trade In Adjoining Room": trade_adj.title() if trade_adj != "LVP" else "LVP",
            "Transition Needed": transition_val,
        })

    outB = pd.DataFrame(outB_rows)

    # Hide rows where Transition Needed == "No"
    if not outB.empty and "Transition Needed" in outB.columns:
        outB = outB[~outB["Transition Needed"].str.strip().str.upper().eq("NO")]

    outB = outB.reset_index(drop=True)

    return outA, outB
