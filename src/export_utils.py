from __future__ import annotations
import io
from typing import Dict, Optional
import pandas as pd

def _safe_sheet(name: str) -> str:
    # Excel sheet name max 31 chars; disallow : \ / ? * [ ]
    bad = [":","\\","/","?","*","[","]"]
    for b in bad:
        name = name.replace(b, "-")
    name = name.strip()
    if len(name) > 31:
        name = name[:31]
    return name or "Sheet"

def build_export_workbook(dfs: Dict[str, pd.DataFrame]) -> bytes:
    """
    dfs: mapping of sheet_name -> dataframe
    returns xlsx bytes
    """
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        for sheet, df in dfs.items():
            if df is None:
                continue
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            df.to_excel(writer, index=False, sheet_name=_safe_sheet(sheet))
    return bio.getvalue()
