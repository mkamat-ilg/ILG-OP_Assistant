from __future__ import annotations
import re
import pandas as pd
from typing import Tuple

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
