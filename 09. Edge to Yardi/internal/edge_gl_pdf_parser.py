"""Parse Edge combined General Ledger PDF into structured rows.

This parser is PDF-layout-aware (PyMuPDF words + column inference).
It is intentionally conservative and geared for month-end automation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF


_MONEY_RE = re.compile(r"\$?\(?-?[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})\)?")
_CODE_RE = re.compile(r"\b\d{4}-\d{4}\b")

# Lines that show up in the PDF but are not part of the table rows.
_NOISE_LINE_RE = re.compile(
    r"^(?:GENERAL\s+LEDGER|REPORT\s+FOR:|Page\s+\d+\s+of\s+\d+|\d+\s+rows)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EdgeGlRow:
    property_name: str
    category: str
    subcategory: str
    description: str
    edge_code: str
    debit: Decimal
    credit: Decimal
    source_page: int  # 1-based


def parse_money(text: str) -> Decimal:
    t = (text or "").strip()
    if not t:
        return Decimal("0")

    # Normal formats seen: "$3,579.00", "$0.00". Also handle parentheses negatives.
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative = True
        t = t[1:-1].strip()

    t = t.replace("$", "").replace(",", "").strip()
    if not t:
        return Decimal("0")

    val = Decimal(t)
    return -val if negative else val


def _is_header_line(cols: dict[str, str]) -> bool:
    return (
        cols.get("Category", "") == "Category"
        and cols.get("Subcategory", "") == "Subcategory"
        and cols.get("Description", "") == "Description"
    )


def _infer_columns_from_headers(words: list[tuple], *, header_y_tolerance: float = 2.0) -> dict[str, float] | None:
    """Return x positions for header labels found on the page."""

    headers = {"Category", "Subcategory", "Description", "Code", "Debit", "Credit"}
    header_words = [w for w in words if w[4] in headers]
    if not header_words:
        return None

    # Find the most common header y (headers are typically aligned).
    y_values = [round(w[1], 1) for w in header_words]
    # pick the smallest y (topmost header row) as anchor
    y_anchor = min(y_values)

    positions: dict[str, float] = {}
    for x0, y0, x1, y1, text, *_rest in header_words:
        if abs(round(y0, 1) - y_anchor) <= header_y_tolerance:
            # Keep the left-most occurrence per header.
            positions[text] = min(positions.get(text, x0), x0)

    if not all(k in positions for k in headers):
        return None

    return positions


def _assign_column(x: float, col_x: dict[str, float]) -> str:
    # Column boundaries: midpoint between adjacent header x's.
    order = ["Category", "Subcategory", "Description", "Code", "Debit", "Credit"]
    xs = [col_x[k] for k in order]
    bounds = [(xs[i] + xs[i + 1]) / 2 for i in range(len(xs) - 1)]

    if x < bounds[0]:
        return "Category"
    if x < bounds[1]:
        return "Subcategory"
    if x < bounds[2]:
        return "Description"
    if x < bounds[3]:
        return "Code"
    if x < bounds[4]:
        return "Debit"
    return "Credit"


def _clean_code_and_description(code_text: str, description_text: str) -> tuple[str, str]:
    """Extract a clean ####-#### code and keep the remaining text as description.

    The PDF sometimes spills words into the Code column (e.g. "Revenue 5805-0000")
    or spills the code into the Description column. We normalize both directions.
    """

    code_raw = (code_text or "").strip()
    desc_raw = (description_text or "").strip()

    # Prefer explicit code matches from either field.
    all_codes = _CODE_RE.findall(code_raw) + _CODE_RE.findall(desc_raw)
    code = all_codes[-1] if all_codes else ""

    # Remove code occurrences from description and code fields.
    if code:
        code_raw = code_raw.replace(code, " ").strip()
        desc_raw = desc_raw.replace(code, " ").strip()

    # If Code column had stray words, push them into the description.
    if code_raw:
        desc_raw = (desc_raw + " " + code_raw).strip() if desc_raw else code_raw

    # Strip common report header/footer fragments that can get merged into the row.
    # Example seen: "Accounts Receivable REPORT FOR: Dec 1st, - Fee".
    desc_raw = re.sub(r"\s+REPORT\s+FOR:\s+[^,]*,", " ", desc_raw, flags=re.IGNORECASE)
    desc_raw = re.sub(r"\bGENERAL\s+LEDGER\b", " ", desc_raw, flags=re.IGNORECASE)

    # Normalize whitespace and commas introduced by PDF wrapping.
    desc_raw = re.sub(r"\s+", " ", desc_raw).replace(" ,", ",").strip()
    return code, desc_raw


def _looks_like_total_row(category: str, subcategory: str, description: str) -> bool:
    cat = (category or "").strip().lower()
    sub = (subcategory or "").strip().lower()
    desc = (description or "").strip().lower()
    if "rows" in cat or "rows" in sub or desc.endswith("rows"):
        return True
    return False


def _iter_lines(words: list[tuple]) -> Iterable[list[tuple]]:
    """Group words into visual lines using y-coordinate clustering.

    PyMuPDF's (block_no, line_no) can split what is visually one row into multiple
    logical lines (notably Debit/Credit). Grouping by y is more robust here.
    """

    by_y: dict[float, list[tuple]] = {}
    for w in words:
        y0 = float(w[1])
        # Bucket y values to reduce noise; 1 decimal has worked well for this PDF.
        key = round(y0, 1)
        by_y.setdefault(key, []).append(w)

    for key in sorted(by_y.keys()):
        ws = by_y[key]
        yield sorted(ws, key=lambda w: w[0])


def extract_rows_from_pdf(
    pdf_path: Path,
    *,
    property_sections: list[dict],
) -> tuple[list[EdgeGlRow], list[str]]:
    """Extract Edge GL rows from the PDF using known property page ranges.

    property_sections is a list of dicts with keys:
      - property_name
      - start_page (1-based)
      - end_page (1-based)
    """

    warnings: list[str] = []
    rows: list[EdgeGlRow] = []

    doc = fitz.open(pdf_path)

    for section in property_sections:
        prop = str(section["property_name"])
        start_page = int(section["start_page"])
        end_page = int(section["end_page"])

        pending: dict[str, str] = {
            "Category": "",
            "Subcategory": "",
            "Description": "",
            "Code": "",
            "Debit": "",
            "Credit": "",
        }

        for page_1based in range(start_page, end_page + 1):
            page = doc.load_page(page_1based - 1)
            words = page.get_text("words") or []
            if not words:
                continue

            col_x = _infer_columns_from_headers(words)
            if not col_x:
                # Some pages may not repeat headers; just skip with warning.
                warnings.append(f"Page {page_1based}: could not infer table columns (missing headers)")
                continue

            for line_words in _iter_lines(words):
                # Build column strings for this line
                cols: dict[str, list[str]] = {k: [] for k in pending}
                for x0, y0, x1, y1, text, *_ in line_words:
                    t = str(text or "").strip()
                    if not t:
                        continue
                    col = _assign_column(float(x0), col_x)
                    cols[col].append(t)

                line_vals = {k: " ".join(v).strip() for k, v in cols.items()}

                # Filter out report/page noise.
                noise_tokens = [line_vals.get(k, "") for k in ("Category", "Subcategory", "Description")]
                if any(_NOISE_LINE_RE.match(tok) for tok in noise_tokens if tok):
                    continue
                # Sometimes the "StorSafe of ..." header lands in the left columns.
                if (line_vals.get("Category", "").lower().startswith("storsafe of") or
                    line_vals.get("Description", "").lower().startswith("storsafe of")):
                    continue

                # Skip header rows.
                if _is_header_line(line_vals):
                    continue

                # Skip any remaining "GENERAL LEDGER" fragments if they slip through.
                if "general" in (line_vals.get("Category", "").lower() + " " + line_vals.get("Subcategory", "").lower()):
                    continue

                # Update pending fields (PDF wraps fields across lines)
                for k in ("Category", "Subcategory", "Description", "Code"):
                    if line_vals.get(k):
                        pending[k] = (pending[k] + " " + line_vals[k]).strip() if pending[k] else line_vals[k]

                # Debit/Credit typically complete a row.
                debit_text = line_vals.get("Debit", "")
                credit_text = line_vals.get("Credit", "")

                # Some pages have stray currency in non-data rows; require at least a description.
                has_money = bool(_MONEY_RE.search(debit_text)) or bool(_MONEY_RE.search(credit_text))
                if not has_money:
                    continue

                # If the line has money but no meaningful text, skip.
                if not (pending["Category"] or pending["Subcategory"] or pending["Description"]):
                    continue

                try:
                    debit = parse_money(debit_text)
                    credit = parse_money(credit_text)
                except Exception:
                    warnings.append(f"Page {page_1based}: could not parse money debit={debit_text!r} credit={credit_text!r}")
                    # Clear pending on failure to avoid cascading corruption.
                    pending = {k: "" for k in pending}
                    continue

                code_clean, desc_clean = _clean_code_and_description(pending["Code"], pending["Description"])

                category_clean = re.sub(r"\s+", " ", (pending["Category"] or "").strip())
                subcategory_clean = re.sub(r"\s+", " ", (pending["Subcategory"] or "").strip())
                if _looks_like_total_row(category_clean, subcategory_clean, desc_clean):
                    pending = {k: "" for k in pending}
                    continue

                rows.append(
                    EdgeGlRow(
                        property_name=prop,
                        category=category_clean,
                        subcategory=subcategory_clean,
                        description=desc_clean,
                        edge_code=code_clean,
                        debit=debit,
                        credit=credit,
                        source_page=page_1based,
                    )
                )

                # Reset for next row
                pending = {k: "" for k in pending}

        # If section ends with partial pending row, warn and drop it.
        if any(pending.values()):
            warnings.append(f"Property {prop}: trailing partial row discarded")

    return rows, warnings
