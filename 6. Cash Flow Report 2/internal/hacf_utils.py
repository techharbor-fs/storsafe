from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable, Sequence


ACCOUNT_CODE_PATTERN = re.compile(r"^\d{4}-\d{4}$")


@dataclass(frozen=True)
class HacfLayout:
    account_code_col: int | None
    description_col: int | None
    property_code_row: int | None  # 0-based
    period_row: int | None  # 0-based
    cfads_row: int | None  # 0-based


def parse_currency(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).replace(",", "").replace("$", "").strip()
    if not text:
        return 0.0

    if "(" in text and ")" in text:
        text = "-" + text.replace("(", "").replace(")", "")

    try:
        return float(text)
    except ValueError:
        return 0.0


def fuzzy_match(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def find_account_columns(table: Sequence[Sequence[object]]) -> tuple[int | None, int | None]:
    """Return (account_code_col, description_col) using a simple scan.

    Looks for cells like '5990-0000'. The adjacent cell is assumed to be description.
    """

    for row in table:
        for col_idx, cell in enumerate(row):
            cell_str = str(cell).strip() if cell is not None else ""
            if cell_str and ACCOUNT_CODE_PATTERN.match(cell_str):
                desc_col = col_idx + 1 if col_idx + 1 < len(row) else None
                return col_idx, desc_col
    return None, None


def find_property_code_row(table: Sequence[Sequence[object]], account_code_col: int | None) -> int | None:
    """Find a row containing many property codes (>=10 short alphanum tokens)."""

    for row_idx, row in enumerate(table):
        code_count = 0
        for col_idx, cell in enumerate(row):
            if account_code_col is not None and col_idx <= account_code_col + 1:
                continue
            cell_str = str(cell).strip() if cell is not None else ""
            if cell_str and len(cell_str) <= 15 and cell_str.replace("-", "").isalnum():
                code_count += 1
        if code_count >= 10:
            return row_idx

    return None


def find_period_row(table: Sequence[Sequence[object]]) -> int | None:
    for row_idx, row in enumerate(table):
        for cell in row:
            cell_lower = str(cell).lower().strip() if cell is not None else ""
            if "period" in cell_lower and ("=" in cell_lower or "202" in cell_lower):
                return row_idx
    return None


def find_cfads_row(table: Sequence[Sequence[object]], description_col: int | None, account_code_col: int | None) -> int | None:
    if description_col is None:
        return None

    for row_idx, row in enumerate(table):
        if len(row) <= description_col:
            continue
        description = str(row[description_col]).strip()
        if "CASH FLOW" not in description.upper():
            continue

        if account_code_col is not None and account_code_col < len(row):
            account_code = str(row[account_code_col]).strip()
            if not account_code:
                return row_idx

    return None


def infer_layout(table: Sequence[Sequence[object]]) -> HacfLayout:
    account_code_col, description_col = find_account_columns(table)
    property_code_row = find_property_code_row(table, account_code_col)
    period_row = find_period_row(table)
    cfads_row = find_cfads_row(table, description_col, account_code_col)

    return HacfLayout(
        account_code_col=account_code_col,
        description_col=description_col,
        property_code_row=property_code_row,
        period_row=period_row,
        cfads_row=cfads_row,
    )


def find_account_row(table: Sequence[Sequence[object]], account_code: str, account_code_col: int | None) -> int | None:
    if account_code_col is None:
        return None

    for row_idx, row in enumerate(table):
        if len(row) <= account_code_col:
            continue
        row_code = str(row[account_code_col]).strip()
        if row_code == account_code:
            return row_idx

    return None


def list_property_codes(table: Sequence[Sequence[object]], property_code_row: int | None, start_col: int) -> list[str]:
    if property_code_row is None or property_code_row >= len(table):
        return []

    row = table[property_code_row]
    codes: list[str] = []
    for cell in row[start_col:]:
        s = str(cell).strip() if cell is not None else ""
        if s:
            codes.append(s)
    return codes


def required_codes() -> list[str]:
    return [
        "5990-0000",
        "7999-9000",
        "7999-9999",
        "8590-0000",
        "2110-0000",
        "2120-0000",
        "2130-0000",
    ]
