from __future__ import annotations
import re
from typing import Dict, Tuple, List, Optional
import pandas as pd

def _norm(s: str) -> str:
    s = "" if s is None else str(s)
    s = s.strip().upper()
    s = re.sub(r"\s+", " ", s)
    return s

def _suggest_category(room: str) -> str:
    r = _norm(room)
    if re.search(r"\bBATH\b|\bPOW\b|\bLAUNDRY\b", r):
        return "Wet Areas"
    if re.search(r"\bBR\b|\bBED\b|\bWIC\b|\bCLOSET\b", r):
        return "Bedrooms"
    if re.search(r"\bGARAGE\b|\bHVAC\b|\bSTORAGE\b|\bPANTRY\b", r):
        return "Garage/Other"
    return "Living Areas"

def build_room_category_map(rooms_df: pd.DataFrame) -> pd.DataFrame:
    df = rooms_df.copy()
    if "Room" not in df.columns:
        df.columns = ["Room"]
    df["Room"] = df["Room"].astype(str)
    return pd.DataFrame({"Room": df["Room"], "Category": [_suggest_category(r) for r in df["Room"]]})


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
    """Build Step 3 outputs with the new requirements.

    Requirements implemented:
      - Output A uses ONLY trades present in Step 1 (no blanket Carpet/LVP/Tile expansion).
      - Every room has exactly ONE trade in Output A.
      - Output B trade comes from Output A (room's trade) and will be recomputed in the UI when Output A changes.

    Notes:
      - We still support Step 1 rows that are category-level (Bedrooms/Living Areas/Wet Areas) or explicit rooms.
      - If there are multiple candidate trades for a room/category, we choose deterministically by the first
        appearance in Step 1, then fall back to a stable priority.
    """
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
            pd.DataFrame(columns=["Room", "Adjoining Room", "Trade", "Transition needed"]),
        )

    # Determine allowed trades (order matters): in-order first appearance from Step 1.
    allowed_trades: List[str] = []
    for t in s1.get("Trade", pd.Series(dtype=str)).tolist():
        k = _trade_key(t)
        if not k:
            continue
        if k not in allowed_trades:
            allowed_trades.append(k)
    if not allowed_trades:
        allowed_trades = ["CARPET", "LVP", "TILE"]

    # Stable fallback priority within whatever trades are present.
    priority = ["CARPET", "LVP", "TILE"]
    allowed_trades = sorted(allowed_trades, key=lambda x: (priority.index(x) if x in priority else 999, allowed_trades.index(x)))

    def cat_key(x: str) -> str:
        x = _norm(x)
        if "BED" in x:
            return "BEDROOMS"
        if "WET" in x or "BATH" in x or "LAUNDRY" in x:
            return "WET AREAS"
        if "LIV" in x or "GREAT" in x or "FOYER" in x or "KIT" in x:
            return "LIVING AREAS"
        return x

    s1["Room_norm"] = s1.get("Room", "").map(_norm)
    s1["Trade_key"] = s1.get("Trade", "").map(_trade_key)
    s1["Cat_norm"] = s1["Room_norm"].map(cat_key)
    known_cats = {"BEDROOMS", "LIVING AREAS", "WET AREAS"}
    s1["IsCategoryRow"] = s1["Cat_norm"].isin(known_cats)

    # Material mapping (prefer explicit rooms, then category).
    room_map: Dict[str, Tuple[str, str]] = {}  # room_norm -> (trade_key, material_desc)
    cat_map: Dict[str, List[Tuple[str, str]]] = {}  # cat_norm -> [(trade_key, material_desc), ...]

    for _, r in s1.iterrows():
        tk = str(r.get("Trade_key", "")).strip()
        if not tk:
            continue
        md = str(r.get("Material Description", "")).strip()
        if r.get("IsCategoryRow", False):
            c = str(r.get("Cat_norm", "")).strip()
            if not c:
                continue
            cat_map.setdefault(c, [])
            # Keep first instance of a given trade per category.
            if all(t != tk for t, _ in cat_map[c]):
                cat_map[c].append((tk, md))
        else:
            rn = str(r.get("Room_norm", "")).strip()
            if not rn:
                continue
            # Keep first mapping for a room.
            if rn not in room_map:
                room_map[rn] = (tk, md)

    # Infer room categories on the fly (3A removed).
    rooms["Room_norm"] = rooms["Room"].map(_norm)
    rooms["Category"] = rooms["Room"].map(_suggest_category)
    rooms["Cat_norm"] = rooms["Category"].map(cat_key)

    outA_rows: List[Dict[str, str]] = []
    for _, rr in rooms.iterrows():
        rn = rr["Room_norm"]

        # 1) Explicit room mapping.
        if rn in room_map:
            tk, md = room_map[rn]
            outA_rows.append({
                "Room": rr["Room"],
                "Trade": tk.title() if tk != "LVP" else "LVP",
                "Material Description": md,
            })
            continue

        # 2) Category mapping.
        cn = rr.get("Cat_norm", "LIVING AREAS")
        candidates = cat_map.get(str(cn), [])
        if candidates:
            # Choose the first candidate whose trade is allowed, otherwise first candidate.
            chosen = None
            for tk in allowed_trades:
                for t, md in candidates:
                    if t == tk:
                        chosen = (t, md)
                        break
                if chosen:
                    break
            if not chosen:
                chosen = candidates[0]
            tk, md = chosen
            outA_rows.append({
                "Room": rr["Room"],
                "Trade": tk.title() if tk != "LVP" else "LVP",
                "Material Description": md,
            })
            continue

        # 3) No mapping found: default to the first allowed trade, blank material.
        tk = allowed_trades[0]
        outA_rows.append({
            "Room": rr["Room"],
            "Trade": tk.title() if tk != "LVP" else "LVP",
            "Material Description": "",
        })

    outA = pd.DataFrame(outA_rows, columns=["Room", "Trade", "Material Description"])

    # Output B will be refined/overridden by the UI based on Output A edits.
    if trans.empty:
        outB = pd.DataFrame(columns=["Room", "Adjoining Room", "Trade", "Transition needed"])
    else:
        trade_by_room = { _norm(r): _trade_key(t) for r, t in zip(outA["Room"].tolist(), outA["Trade"].tolist()) }
        outB_rows: List[Dict[str, str]] = []
        for _, tr in trans.iterrows():
            room = str(tr.get("Room", ""))
            tk = trade_by_room.get(_norm(room), allowed_trades[0])
            outB_rows.append({
                "Room": room,
                "Adjoining Room": str(tr.get("Adjoining Room", "")),
                "Trade": tk.title() if tk != "LVP" else "LVP",
                "Transition needed": str(tr.get("Transition needed", "")),
            })
        outB = pd.DataFrame(outB_rows, columns=["Room", "Adjoining Room", "Trade", "Transition needed"])

    return outA, outB

def apply_step3_merge(step1_df: pd.DataFrame, rooms_df: pd.DataFrame, transitions_df: pd.DataFrame, room_category_map_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s1 = step1_df.copy()
    rooms = rooms_df.copy()
    trans = transitions_df.copy()
    m = room_category_map_df.copy()

    for df, col in [(s1,"Room"),(s1,"Trade"),(rooms,"Room"),(trans,"Room"),(trans,"Adjoining Room"),(m,"Room"),(m,"Category")]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    def cat_key(x: str) -> str:
        x = _norm(x)
        if "BED" in x: return "BEDROOMS"
        if "WET" in x or "BATH" in x or "LAUNDRY" in x: return "WET AREAS"
        if "LIV" in x or "GREAT" in x or "FOYER" in x or "KIT" in x: return "LIVING AREAS"
        return x

    s1["Room_norm"] = s1.get("Room", "").map(_norm)
    s1["Trade_norm"] = s1.get("Trade", "").map(_norm)
    s1["Cat_norm"] = s1["Room_norm"].map(cat_key)
    known_cats = {"BEDROOMS","LIVING AREAS","WET AREAS"}
    s1["IsCategoryRow"] = s1["Cat_norm"].isin(known_cats)

    room_trade = {}
    cat_trade = {}

    for _, r in s1.iterrows():
        t = r.get("Trade_norm","")
        mat = str(r.get("Material Description","")).strip()
        if not t:
            continue
        if r.get("IsCategoryRow", False):
            c = r.get("Cat_norm","")
            if c:
                cat_trade[(c,t)] = mat
        else:
            rm = r.get("Room_norm","")
            if rm:
                room_trade[(rm,t)] = mat

    m["Room_norm"] = m["Room"].map(_norm)
    m["Cat_norm"] = m["Category"].map(cat_key)
    room_to_cat = dict(zip(m["Room_norm"], m["Cat_norm"]))

    rooms["Room_norm"] = rooms["Room"].map(_norm)
    trades = ["CARPET","LVP","TILE"]

    outA_rows, diag_rows = [], []
    for _, rr in rooms.iterrows():
        rn = rr["Room_norm"]
        cat = room_to_cat.get(rn, "LIVING AREAS")
        for t in trades:
            mat, src = "", "Unmatched"
            if (rn,t) in room_trade:
                mat, src = room_trade[(rn,t)], "Explicit room"
            elif (cat,t) in cat_trade:
                mat, src = cat_trade[(cat,t)], f"Category: {cat}"
            outA_rows.append({"Room": rr["Room"], "Trade": t.title() if t!="LVP" else "LVP", "Material Description": mat})
            diag_rows.append({"Room": rr["Room"], "Trade": t.title() if t!="LVP" else "LVP", "Mapped Category": cat.title(), "Material Source": src})

    outA = pd.DataFrame(outA_rows)

    if trans.empty:
        outB = pd.DataFrame(columns=["Room","Adjoining Room","Trade","Transition needed"])
    else:
        outB_rows = []
        for _, tr in trans.iterrows():
            for t in trades:
                outB_rows.append({"Room": tr.get("Room",""), "Adjoining Room": tr.get("Adjoining Room",""), "Trade": t.title() if t!="LVP" else "LVP", "Transition needed": tr.get("Transition needed","")})
        outB = pd.DataFrame(outB_rows)

    diagnostics = pd.DataFrame(diag_rows)
    return outA, outB, diagnostics
