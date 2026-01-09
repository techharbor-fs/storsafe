"""Normalize Transaction Description

This script reads transaction descriptions from Column I of the Due To/From GL - 08.31.25 sheet,
removes property references (recorder and counterparty), normalizes the core business purpose,
and outputs the result to Column K. Unique normalized descriptions are tracked in the
Transaction DB sheet.

The script processes rows in batches and uses OpenAI for complex normalization cases.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

import gspread
from openai import OpenAI

# Default Google Sheet that holds the property database and classify sheet
DEFAULT_SHEET_ID = "1LKwP5e61ci10mtQm3MytN8_WuPgxcm2R-L6hB003zoY"
PROPERTY_SHEET_NAME = "Property DB"
CLASSIFY_SHEET_NAME = "Due To/From GL - 08.31.25"  # Updated sheet name
TRANSACTION_DB_SHEET_NAME = "Transaction DB"
DEFAULT_BATCH_SIZE = 25
DEFAULT_MODEL = "gpt-4o"

logger = logging.getLogger("transaction_normalizer")


def _resolve_service_account_path(project_root: Path, override_path: Optional[str]) -> Path:
    """Resolve Google service account JSON path.

    Priority:
    1) SERVICE_ACCOUNT_JSON (inline JSON; written to a temp file)
    2) --service-account CLI arg
    3) GOOGLE_APPLICATION_CREDENTIALS / SERVICE_ACCOUNT_FILE

    If a resolved path is relative, it is resolved against project_root.
    """
    service_account_json = os.environ.get("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        temp_json_path = Path(tempfile.gettempdir()) / f"storsafe_service_account_{os.getpid()}.json"
        temp_json_path.write_text(json.dumps(json.loads(service_account_json)), encoding="utf-8")
        return temp_json_path

    env_path = override_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("SERVICE_ACCOUNT_FILE")
    if not env_path:
        raise ValueError(
            "Missing Google service account credentials. Set SERVICE_ACCOUNT_JSON or "
            "GOOGLE_APPLICATION_CREDENTIALS/SERVICE_ACCOUNT_FILE, or pass --service-account."
        )

    resolved = Path(env_path)
    if not resolved.is_absolute():
        resolved = (project_root / resolved).resolve()
    return resolved


def _resolve_openai_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("OPEN_AI_API_KEY")
    if not api_key:
        raise ValueError("Missing OpenAI API key. Set OPENAI_API_KEY (or legacy OPEN_AI_API_KEY).")
    return api_key


@dataclass
class PropertyEntry:
    code: str
    aliases: List[str]
    raw_name: str = ""
    alias_set: Set[str] = field(init=False)

    def __post_init__(self) -> None:
        alias_candidates: Set[str] = {self.code}
        alias_candidates.update(self.aliases)
        if self.raw_name:
            alias_candidates.add(self.raw_name)
        self.alias_set = {alias.strip() for alias in alias_candidates if alias.strip()}


class PropertyDatabase:
    def __init__(self, rows: Sequence[Sequence[str]]):
        if not rows:
            raise ValueError("Property database sheet is empty")
        self.entries: List[PropertyEntry] = []
        self.all_property_references: Set[str] = set()
        self._build(rows)

    @staticmethod
    def _split_aliases(raw: str) -> List[str]:
        if not raw:
            return []
        parts = re.split(r"[,/;|\n]+", raw)
        return [part.strip() for part in parts if part and part.strip()]

    def _build(self, rows: Sequence[Sequence[str]]) -> None:
        for row in rows[1:]:
            code = row[0].strip() if len(row) > 0 else ""
            name = row[1].strip() if len(row) > 1 else ""
            if not code:
                continue
            aliases = self._split_aliases(name)
            entry = PropertyEntry(code=code, aliases=aliases, raw_name=name)
            self.entries.append(entry)
            
            # Add all property references for removal
            for alias in entry.alias_set:
                self.all_property_references.add(alias.lower())

    def remove_property_references(self, text: str) -> str:
        """Remove all property code and alias references from text"""
        if not text:
            return text
        
        # Start with the original text
        cleaned_text = text
        
        # Remove property references (case insensitive)
        for prop_ref in sorted(self.all_property_references, key=len, reverse=True):
            # Use word boundaries for exact matches
            pattern = r'\b' + re.escape(prop_ref) + r'\b'
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)
        
        # Clean up extra spaces, pipes, and punctuation
        cleaned_text = re.sub(r'\s*\|\s*', ' | ', cleaned_text)  # Normalize pipes
        cleaned_text = re.sub(r'\s*-\s*', ' - ', cleaned_text)   # Normalize dashes
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)         # Multiple spaces to single
        cleaned_text = cleaned_text.strip(' |-')                # Trim spaces, pipes, dashes
        
        return cleaned_text


class TransactionNormalizer:
    def __init__(
        self,
        sheet_id: str,
        service_account_path: Path,
        openai_key: str,
        model: str = DEFAULT_MODEL,
    ):
        self.sheet_id = sheet_id
        self.client = gspread.service_account(filename=str(service_account_path))
        self.workbook = self.client.open_by_key(sheet_id)
        self.property_sheet = self.workbook.worksheet(PROPERTY_SHEET_NAME)
        self.classify_sheet = self.workbook.worksheet(CLASSIFY_SHEET_NAME)
        self.transaction_db_sheet = self.workbook.worksheet(TRANSACTION_DB_SHEET_NAME)
        self.property_db = PropertyDatabase(self.property_sheet.get_all_values())
        self.openai = OpenAI(api_key=openai_key)
        self.model = model
        self.processed_descriptions: Set[str] = set()

    def fetch_pending_rows(self, reprocess_all: bool = False) -> List[Dict[str, str]]:
        values = self.classify_sheet.get_all_values()
        pending: List[Dict[str, str]] = []
        for idx, row in enumerate(values, start=1):
            if idx == 1:
                continue  # header row
            recorder = row[0].strip() if len(row) > 0 else ""
            description = row[8].strip() if len(row) > 8 else ""  # Column I (index 8)
            counterparty = row[9].strip() if len(row) > 9 else ""  # Column J (index 9) 
            existing_normalized = row[10].strip() if len(row) > 10 else ""  # Column K (index 10)
            
            if not description:
                continue
            
            # Reprocess all mode: process all rows with descriptions
            if reprocess_all:
                pass  # Process all rows
            # Standard mode: only process empty or "unknown"
            elif existing_normalized and existing_normalized.lower() != "unknown":
                continue
                
            pending.append(
                {
                    "row": idx,
                    "recorder": recorder,
                    "description": description,
                    "counterparty": counterparty,
                }
            )
        return pending

    def normalize_with_rules(self, description: str) -> Optional[str]:
        """Apply rule-based normalization for common patterns"""
        desc_lower = description.lower()
        
        # Handle Capturis transactions first
        if "capturis" in desc_lower:
            return "Capturis error"
        
        # Extract 3rd party (entities not in property database)
        third_party = self._extract_third_party(description)
        
        # Determine purpose with more specific patterns
        if any(phrase in desc_lower for phrase in ["for cover", "for loan cover"]):
            return f"Payment for general expenses{' - ' + third_party if third_party else ''}"
        elif "transfer" in desc_lower and len(description.split()) <= 3:
            return f"Payment for general expenses{' - ' + third_party if third_party else ''}"
        
        # Specific loan purposes
        elif "loan deposit" in desc_lower:
            return f"Payment for loan deposit{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["loan fees refunded", "loan fee refund"]):
            return f"Payment for loan fees refunded{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["for loan", "loan funding"]):
            return f"Payment for loan{' - ' + third_party if third_party else ''}"
        
        # Chase payments are general expenses
        elif third_party and third_party.lower() == "chase":
            return f"Payment for general expenses"
        
        # Tax and insurance combinations
        elif any(phrase in desc_lower for phrase in ["tax & ins", "t&i", "tax and insurance"]):
            return f"Payment for tax and insurance{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["property tax", "tax payment"]):
            return f"Payment for taxes{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["insurance", "ins to"]):
            return f"Payment for insurance{' - ' + third_party if third_party else ''}"
        
        # Other services
        elif any(phrase in desc_lower for phrase in ["disposal", "trash", "waste"]):
            return f"Payment for waste management{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["janitorial", "cleaning"]):
            return f"Payment for services{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["draw ", "cm & dev fee", "construction"]):
            return f"Payment for construction{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["management fee", "property management"]):
            return f"Payment for services{' - ' + third_party if third_party else ''}"
        elif any(phrase in desc_lower for phrase in ["return", "repay", "refund"]):
            # For returns, try to identify original purpose from context
            if "loan" in desc_lower:
                return f"Payment for loan{' - ' + third_party if third_party else ''}"
            elif "insurance" in desc_lower:
                return f"Payment for insurance{' - ' + third_party if third_party else ''}"
            else:
                return f"Payment for general expenses{' - ' + third_party if third_party else ''}"
        
        return None

    def _extract_third_party(self, description: str) -> Optional[str]:
        """Extract third party entity (not a property entity)"""
        # Split description and clean up
        parts = re.split(r'[|,;]', description)
        
        # Known entity mappings for proper capitalization
        entity_mappings = {
            'chase': 'Chase',
            'peoples bank': 'Peoples Bank',
            'wells fargo': 'Wells Fargo',
            'bank of america': 'Bank of America',
            'us bank': 'US Bank',
            'capone': 'CapOne',
            'city of crown point': None,  # This is cpwest - property entity, exclude
        }
        
        # Common bank/entity patterns - order matters for proper matching
        bank_patterns = [
            # Multi-word company names first
            r'\b([A-Z][A-Za-z\s]+ Services LLC)\b',
            r'\b([A-Z][A-Za-z\s]+ Management Inc\.?)\b',
            r'\b([A-Z][A-Za-z\s]+ Insurance)\b',
            r'\b([A-Z][A-Za-z\s]+Bank)\b',
            # Specific known entities
            r'\b(Peoples Bank|Chase|Wells Fargo|Bank of America|US Bank|CapOne)\b',
            r'\b(Waste Management Inc\.?)\b',
            # Generic patterns last
            r'\b([A-Z][A-Za-z]+ Bank)\b',
            r'\b([A-Z][A-Za-z]+ Inc\.?)\b',
            r'\b([A-Z][A-Za-z]+ LLC)\b',
            r'\b([A-Z][A-Za-z]+ Corp\.?)\b',
        ]
        
        for part in parts:
            part_clean = part.strip()
            
            # Skip transfer intermediaries
            if any(skip in part_clean.lower() for skip in ['via ', 'through ', 'thru ']):
                continue
            
            # Check known entity mappings first
            part_lower = part_clean.lower()
            for known_entity, proper_name in entity_mappings.items():
                if known_entity in part_lower:
                    if proper_name is None:  # Explicitly excluded entity
                        continue
                    # Verify it's not a property entity
                    if known_entity not in self.property_db.all_property_references:
                        return proper_name
                
            # Check against bank/entity patterns
            for pattern in bank_patterns:
                match = re.search(pattern, part_clean, re.IGNORECASE)
                if match:
                    entity = match.group(1).strip()
                    entity_lower = entity.lower()
                    
                    # Apply proper capitalization
                    if entity_lower in entity_mappings:
                        entity = entity_mappings[entity_lower]
                        if entity is None:  # Excluded entity
                            continue
                    
                    # Verify it's not a property entity
                    if entity_lower not in self.property_db.all_property_references:
                        return entity
        
        return None

    def process_batches(self, batch_size: int = DEFAULT_BATCH_SIZE, max_batches: Optional[int] = None, reprocess_all: bool = False) -> None:
        pending = self.fetch_pending_rows(reprocess_all=reprocess_all)
        if not pending:
            logger.info("No pending rows to normalize.")
            return

        total_rows = len(pending)
        batches_processed = 0
        for start in range(0, total_rows, batch_size):
            if max_batches is not None and batches_processed >= max_batches:
                break
            current_batch = pending[start : start + batch_size]
            logger.info(
                "Processing batch %s with %s rows (rows %s-%s)",
                batches_processed + 1,
                len(current_batch),
                current_batch[0]["row"],
                current_batch[-1]["row"],
            )
            self._process_batch(current_batch)
            batches_processed += 1

        logger.info("Completed %s batches (%s rows updated where possible).", batches_processed, total_rows)

    def _process_batch(self, batch: Sequence[Dict[str, str]]) -> None:
        updates: List[Dict[str, str]] = []
        unresolved: List[Dict[str, str]] = []
        new_descriptions: Set[str] = set()

        for record in batch:
            # Remove property references from description
            cleaned_desc = self.property_db.remove_property_references(record["description"])
            
            # Try rule-based normalization first
            normalized = self.normalize_with_rules(cleaned_desc)
            
            if normalized:
                logger.debug("Row %s resolved via rules: %s", record["row"], normalized)
                updates.append({"row": record["row"], "value": normalized})
                new_descriptions.add(normalized)
            else:
                # Prepare for AI processing
                unresolved.append({
                    **record,
                    "cleaned_description": cleaned_desc
                })

        if unresolved:
            ai_results = self._normalize_with_ai(unresolved)
            for row, value in ai_results.items():
                if value:
                    updates.append({"row": row, "value": value})
                    new_descriptions.add(value)

        if updates:
            # Update Column K in Due To/From GL - 08.31.25 sheet
            request_body = [
                {
                    "range": f"K{item['row']}",
                    "values": [[item["value"]]],
                }
                for item in updates
            ]
            self.classify_sheet.batch_update(request_body)
            logger.info("Updated %s rows in current batch.", len(updates))
            
            # Update Transaction DB with new unique descriptions
            self._update_transaction_db(new_descriptions)
        else:
            logger.info("No updates produced for this batch.")

    def _normalize_with_ai(self, pending: Sequence[Dict[str, str]]) -> Dict[int, str]:
        prompt_payload = {
            "instructions": [
                "Normalize transaction descriptions using this EXACT format: 'Payment for [specific purpose] - [3rd Party]' or 'Payment for [specific purpose]' if no 3rd party.",
                "Use SPECIFIC purposes like 'loan deposit', 'loan fees refunded', 'tax and insurance', not generic terms.",
                "For Capturis transactions, return 'Capturis error'.",
                "Chase transactions are general expenses: 'Payment for general expenses' (no 3rd party).",
                "Use 'general expenses' (plural) not 'general expense'.",
                "Use proper capitalization: 'Chase' not 'chase', 'Peoples Bank' not 'peoples bank'.",
                "Exclude property entities as 3rd parties (City of Crown Point = cpwest property entity).",
                "Ignore transfer intermediaries (via, through, thru).",
                "Format must be exact - start with 'Payment for' followed by specific purpose, then '- EntityName' if applicable."
            ],
            "examples": [
                {"input": "Loan deposit to Peoples Bank", "output": "Payment for loan deposit - Peoples Bank"},
                {"input": "Loan fees refunded from Peoples Bank", "output": "Payment for loan fees refunded - Peoples Bank"},
                {"input": "Chase payment for expenses", "output": "Payment for general expenses"},
                {"input": "Tax and Insurance payment", "output": "Payment for tax and insurance"},
                {"input": "Capturis processing fee", "output": "Capturis error"},
                {"input": "City of Crown Point utility", "output": "Payment for utilities"}
            ],
            "transactions": [
                {
                    "row": record["row"],
                    "original": record["description"],
                    "cleaned": record["cleaned_description"],
                }
                for record in pending
            ],
        }

        response = self.openai.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a meticulous accounting assistant that normalizes transaction descriptions and outputs valid JSON."},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Normalize transaction descriptions using format 'Payment for [purpose] - [3rd Party]' or 'Payment for [purpose]'.",
                            "payload": prompt_payload,
                            "response_format": "Return a JSON object where keys are row numbers and values are normalized descriptions in the specified format.",
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
        )

        output_text = response.choices[0].message.content.strip()
        logger.debug("AI raw response: %s", output_text)

        # Handle markdown code blocks that OpenAI sometimes returns
        if output_text.startswith("```json"):
            output_text = output_text[7:]  # Remove ```json
        if output_text.startswith("```"):
            output_text = output_text[3:]   # Remove ```
        if output_text.endswith("```"):
            output_text = output_text[:-3]  # Remove trailing ```
        output_text = output_text.strip()

        try:
            result_map = json.loads(output_text)
        except json.JSONDecodeError:
            logger.error("Failed to parse AI response; marking rows as unknown.")
            return {record["row"]: "unknown" for record in pending}

        parsed: Dict[int, str] = {}
        for record in pending:
            key = str(record["row"])
            value = result_map.get(key)
            if not value:
                parsed[record["row"]] = "unknown"
            else:
                parsed[record["row"]] = str(value).strip()
        return parsed

    def _update_transaction_db(self, new_descriptions: Set[str]) -> None:
        """Update Transaction DB sheet with new unique descriptions"""
        if not new_descriptions:
            return
        
        # Get existing descriptions from Transaction DB
        existing_values = self.transaction_db_sheet.get_all_values()
        existing_descriptions = {row[0].strip().lower() for row in existing_values if row and row[0].strip()}
        
        # Filter out descriptions that already exist
        truly_new = []
        for desc in new_descriptions:
            if desc.lower() not in existing_descriptions:
                truly_new.append([desc])
        
        if truly_new:
            # Find the next empty row
            next_row = len(existing_values) + 1
            
            # Add new descriptions to Transaction DB
            range_name = f"A{next_row}:A{next_row + len(truly_new) - 1}"
            self.transaction_db_sheet.update(values=truly_new, range_name=range_name)
            logger.info("Added %s new descriptions to Transaction DB.", len(truly_new))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize transaction descriptions in Google Sheets.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="Target Google Sheet ID (default: provided ID)")
    parser.add_argument("--service-account", default=None, help="Override path to the Google service account JSON file")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Number of rows to process per batch (default: 25)")
    parser.add_argument("--max-batches", type=int, default=None, help="Optional limit on number of batches to process")
    parser.add_argument("--reprocess-all", action="store_true", help="Reprocess all existing normalized descriptions to new format")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model to use (default: gpt-4o-mini)")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s | %(message)s")

    # StorSafe project root (this file lives under: <storsafe_root>/1. Account Reconciliation/)
    try:
        project_root = Path(__file__).resolve().parents[1]
    except NameError:
        project_root = Path.cwd()

    service_account_path = _resolve_service_account_path(project_root, args.service_account)
    if not service_account_path.exists():
        raise FileNotFoundError(f"Service account file not found: {service_account_path}")

    openai_key = _resolve_openai_api_key()

    normalizer = TransactionNormalizer(
        sheet_id=args.sheet_id,
        service_account_path=service_account_path,
        openai_key=openai_key,
        model=args.model,
    )

    if args.reprocess_all:
        logger.warning("REPROCESS ALL mode: Will update ALL existing normalized descriptions to new format")
    
    normalizer.process_batches(batch_size=args.batch_size, max_batches=args.max_batches, reprocess_all=args.reprocess_all)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error while normalizing transaction descriptions: %s", exc)
        sys.exit(1)