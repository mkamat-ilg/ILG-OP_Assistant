import math
import re
from typing import Dict, Optional

CELL_REF_RE = re.compile(r"\$?([A-Z]+)\$?(\d+)")
SUM_RE = re.compile(r"SUM\(([^)]+)\)", re.IGNORECASE)

def _mround(x: float, m: float) -> float:
    if m == 0:
        return 0.0
    return round(x / m) * m

def _roundup(x: float, digits: int) -> float:
    factor = 10 ** int(digits)
    if x >= 0:
        return math.ceil(x * factor) / factor
    return -math.ceil(abs(x) * factor) / factor

def eval_excel_formula(formula: str, cell_map: Dict[str, float]) -> Optional[float]:
    """
    Very small safe evaluator for common workbook patterns.
    Supports:
      - arithmetic + - * / ( )
      - SUM(J2) and SUM($J$2) and SUM($J$2:$J$10) (single-column ranges)
      - MROUND(x,m), ROUNDUP(x,digits), CEILING(x,s), FLOOR(x,s), ABS, MIN, MAX, ROUND
      - cell refs like J2, $J$2
    Returns None when unsupported.
    """
    if not isinstance(formula, str) or not formula.startswith("="):
        return None

    expr = formula[1:].strip()

    # Expand SUM()
    def sum_repl(match):
        inside = match.group(1).replace("$", "").strip()
        if ":" in inside:
            start, end = inside.split(":")
            m1 = CELL_REF_RE.fullmatch(start.strip())
            m2 = CELL_REF_RE.fullmatch(end.strip())
            if not (m1 and m2):
                raise ValueError("bad range")
            col1, r1 = m1.group(1), int(m1.group(2))
            col2, r2 = m2.group(1), int(m2.group(2))
            if col1 != col2:
                raise ValueError("multi-col range")
            lo, hi = min(r1, r2), max(r1, r2)
            total = 0.0
            for r in range(lo, hi + 1):
                total += float(cell_map.get(f"{col1}{r}", 0.0))
            return str(total)
        m = CELL_REF_RE.fullmatch(inside)
        if not m:
            raise ValueError("bad arg")
        key = f"{m.group(1)}{int(m.group(2))}"
        return str(float(cell_map.get(key, 0.0)))

    try:
        expr = SUM_RE.sub(sum_repl, expr)
    except Exception:
        return None

    # Replace cell refs with numbers
    def cell_repl(match):
        col, row = match.group(1), int(match.group(2))
        return str(float(cell_map.get(f"{col}{row}", 0.0)))

    expr = CELL_REF_RE.sub(cell_repl, expr)

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
    }

    # If any identifiers remain, refuse
    if re.search(r"[A-Za-z_]{2,}", expr):
        return None

    try:
        val = eval(expr, safe_globals, {})
        return float(val)
    except Exception:
        return None
