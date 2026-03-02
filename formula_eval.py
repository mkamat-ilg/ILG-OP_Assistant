import math
import re
from typing import Dict, Optional

CELL_REF_RE = re.compile(r"\$?([A-Z]+)\$?(\d+)")
SUM_RE = re.compile(r"SUM\(([^)]+)\)", re.IGNORECASE)

def _col_to_index(col: str) -> int:
    idx = 0
    for c in col:
        idx = idx * 26 + (ord(c) - ord("A") + 1)
    return idx

def _mround(x: float, m: float) -> float:
    if m == 0:
        return 0.0
    return round(x / m) * m

def _roundup(x: float, digits: int) -> float:
    # Excel ROUNDUP(x,0) => ceil(|x|) with sign preserved
    factor = 10 ** digits
    if x >= 0:
        return math.ceil(x * factor) / factor
    return -math.ceil(abs(x) * factor) / factor

def eval_excel_formula(formula: str, cell_map: Dict[str, float]) -> Optional[float]:
    """
    Supports:
      - basic arithmetic: + - * / ( )
      - MROUND(x, m)
      - ROUNDUP(x, digits)
      - SUM(J2) and SUM($J$2) and SUM($J$2:$J$10) [simple ranges on same column]
      - cell refs like J2, $J$2
    Returns None if unsupported.
    """
    if not isinstance(formula, str) or not formula.startswith("="):
        return None

    expr = formula[1:].strip()

    # normalize separators
    expr = expr.replace("^", "**")  # rarely used; allowed if present

    # SUM handling (very limited, single-column ranges)
    def sum_repl(match):
        inside = match.group(1).replace("$", "").strip()
        if ":" in inside:
            start, end = inside.split(":")
            m1 = CELL_REF_RE.fullmatch(start.strip())
            m2 = CELL_REF_RE.fullmatch(end.strip())
            if not (m1 and m2):
                raise ValueError("Unsupported SUM range")
            col1, r1 = m1.group(1), int(m1.group(2))
            col2, r2 = m2.group(1), int(m2.group(2))
            if col1 != col2:
                raise ValueError("Unsupported multi-col SUM")
            lo, hi = min(r1, r2), max(r1, r2)
            total = 0.0
            for r in range(lo, hi + 1):
                key = f"{col1}{r}"
                total += float(cell_map.get(key, 0.0))
            return str(total)

        m = CELL_REF_RE.fullmatch(inside)
        if not m:
            raise ValueError("Unsupported SUM arg")
        key = f"{m.group(1)}{int(m.group(2))}"
        return str(float(cell_map.get(key, 0.0)))

    try:
        expr = SUM_RE.sub(sum_repl, expr)
    except Exception:
        return None

    # Replace cell refs with values
    def cell_repl(match):
        col, row = match.group(1), int(match.group(2))
        key = f"{col}{row}"
        return str(float(cell_map.get(key, 0.0)))

    expr = CELL_REF_RE.sub(cell_repl, expr)

    # Map allowed functions
    safe_globals = {
        "__builtins__": {},
        "MROUND": _mround,
        "ROUNDUP": _roundup,
        "CEILING": lambda x, s: math.ceil(x / s) * s if s else 0.0,
        "FLOOR": lambda x, s: math.floor(x / s) * s if s else 0.0,
        "ABS": abs,
        "MIN": min,
        "MAX": max,
        "ROUND": round,
        "math": math,
    }

    # hard deny other tokens (very conservative)
    if re.search(r"[A-Za-z_]{3,}", expr):
        # if any word-like token remains, it's something unsupported
        return None

    try:
        val = eval(expr, safe_globals, {})
        if val is None:
            return None
        return float(val)
    except Exception:
        return None
