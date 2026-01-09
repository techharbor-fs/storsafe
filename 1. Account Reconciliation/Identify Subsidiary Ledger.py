"""Identify Subsidiary Ledger

This script reads transactions from the "Classify" sheet of the target Google Sheet,
leverages a property database stored in the "Property DB" sheet, and identifies the
counterparty property code for each description. The results are written back to
column C of the "Classify" sheet.

The script processes rows in batches (default 25) and falls back to an OpenAI model
when deterministic matching against the property database is inconclusive.
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
from typing import Dict, Iterable, List, Optional, Sequence, Set

import gspread
from openai import OpenAI

# Default Google Sheet that holds the property database and classify sheet
DEFAULT_SHEET_ID = "1LKwP5e61ci10mtQm3MytN8_WuPgxcm2R-L6hB003zoY"
PROPERTY_SHEET_NAME = "Property DB"
CLASSIFY_SHEET_NAME = "Due To/From GL - 08.31.25"
DEFAULT_BATCH_SIZE = 12  # Reduced from 25 for more focused AI processing
DEFAULT_MODEL = "gpt-4o"  # Upgraded from gpt-4o-mini for better accuracy

logger = logging.getLogger("subsidiary_ledger")


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
        self.alias_map_raw: Dict[str, str] = {}
        self.alias_map_normalized: Dict[str, str] = {}
        self.original_rows = rows
        self.normalized_rows = self._normalize_property_data(rows)
        self._build(self.normalized_rows)

    @staticmethod
    def _split_aliases(raw: str) -> List[str]:
        if not raw:
            return []
        parts = re.split(r"[,/;|\n]+", raw)
        return [part.strip() for part in parts if part and part.strip()]

    @staticmethod
    def _normalize(text: str) -> str:
        """Enhanced normalization for consistent text processing"""
        if not text:
            return ""
        # Convert to lowercase and normalize spacing/punctuation
        cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
        return re.sub(r"\s+", " ", cleaned).strip()
    
    @staticmethod
    def _normalize_property_data(property_rows: list) -> list:
        """Normalize all Property DB data to lowercase for consistent matching"""
        normalized_rows = []
        for row in property_rows:
            if not row:
                continue
            normalized_row = []
            for cell in row:
                if isinstance(cell, str):
                    normalized_row.append(cell.lower())
                else:
                    normalized_row.append(str(cell).lower() if cell else "")
            normalized_rows.append(normalized_row)
        return normalized_rows

    def _add_alias(self, alias: str, code: str) -> None:
        lowered = alias.lower()
        if lowered:
            self.alias_map_raw[lowered] = code
        normalized = self._normalize(alias)
        if normalized:
            self.alias_map_normalized[normalized] = code

    def _build(self, rows: Sequence[Sequence[str]]) -> None:
        for row in rows[1:]:
            code = row[0].strip() if len(row) > 0 else ""
            name = row[1].strip() if len(row) > 1 else ""
            if not code:
                continue
            aliases = self._split_aliases(name)
            entry = PropertyEntry(code=code, aliases=aliases, raw_name=name)
            self.entries.append(entry)
            for alias in entry.alias_set:
                self._add_alias(alias, code)

    def identify_codes(self, text: str) -> Set[str]:
        if not text:
            return set()
        text_lower = text.lower()
        normalized = self._normalize(text)
        matches: Set[str] = set()
        
        # Enhanced matching with priority for longer, more specific aliases
        import re
        
        # Collect all potential matches with their alias lengths for prioritization
        potential_matches = []
        
        for entry in self.entries:
            for alias in entry.alias_set:
                if alias and len(alias) >= 2:
                    alias_lower = alias.lower()
                    alias_normalized = self._normalize(alias)
                    
                    # Check for exact word boundary matches (highest priority)
                    pattern = r'\b' + re.escape(alias_lower) + r'\b'
                    if re.search(pattern, text_lower):
                        potential_matches.append((len(alias), entry.code, alias, 'word_boundary'))
                    
                    # Check for partial matches within words (lower priority)
                    elif alias_lower in text_lower:
                        potential_matches.append((len(alias), entry.code, alias, 'substring'))
                    
                    # Check normalized matches
                    elif alias_normalized and alias_normalized in normalized:
                        potential_matches.append((len(alias), entry.code, alias, 'normalized'))
        
        # Sort by alias length (longer = more specific = higher priority)
        potential_matches.sort(key=lambda x: x[0], reverse=True)
        
        # Add matches, giving preference to longer, more specific aliases
        added_codes = set()
        for length, code, alias, match_type in potential_matches:
            # For MSS2 specifically, ensure it goes to ssmsouth
            if alias.lower() == 'mss2' and code == 'ssmsouth':
                matches.add(code)
                added_codes.add(code)
            # For other matches, avoid conflicts with already added codes
            elif code not in added_codes:
                matches.add(code)
                added_codes.add(code)
        
        return matches

    def identify_primary_code(self, text: str) -> Optional[str]:
        matches = self.identify_codes(text)
        if len(matches) == 1:
            return next(iter(matches))
        return None

    def identify_counterparty_enhanced(self, recorder: str, description: str) -> Optional[str]:
        """
        Enhanced counterparty identification using the detailed algorithm:
        
        Step-by-step process:
        1. Normalize the transaction description to lowercase
        2. Identify the recorder entity in the normalized description
        3. Remove/filter out recorder entity mentions from the description
        4. Search the processed description against the normalized Property DB
        5. Return the property code of the counterparty, or "unknown" if no match
        """
        if not description:
            return None
            
        # Step 1: Normalize the transaction description
        normalized_description = self._normalize(description)
        logger.debug(f"Normalized description: '{normalized_description}'")
        
        # Step 2: Identify recorder entity and its aliases in the description
        recorder_matches = self.identify_codes(recorder)
        logger.debug(f"Recorder '{recorder}' matches: {recorder_matches}")
        
        # Step 3: Remove recorder entity mentions from the normalized description
        processed_description = normalized_description
        if recorder_matches:
            for entry in self.entries:
                if entry.code in recorder_matches:
                    # Remove all aliases of the recorder entity from the description
                    for alias in entry.alias_set:
                        alias_normalized = self._normalize(alias)
                        if alias_normalized and alias_normalized in processed_description:
                            processed_description = processed_description.replace(alias_normalized, " ")
                            logger.debug(f"Removed recorder alias '{alias_normalized}' from description")
        
        # Clean up the processed description
        processed_description = re.sub(r"\s+", " ", processed_description).strip()
        logger.debug(f"Processed description after recorder removal: '{processed_description}'")
        
        # Step 4: Search for counterparty in the processed description
        counterparty_matches = self.identify_codes(processed_description)
        logger.debug(f"Counterparty matches in processed description: {counterparty_matches}")
        
        # Step 5: Return the counterparty property code
        if len(counterparty_matches) == 1:
            result = next(iter(counterparty_matches))
            logger.debug(f"Single counterparty identified: {result}")
            return result
        elif len(counterparty_matches) > 1:
            # Multiple matches - apply priority rules
            if 'ssmsouth' in counterparty_matches and 'mss2' in description.lower():
                logger.debug("Applied MSS2 → ssmsouth priority rule")
                return 'ssmsouth'
            # Return the longest/most specific match
            longest_match = max(counterparty_matches, key=lambda x: len(x))
            logger.debug(f"Multiple matches, returning longest: {longest_match}")
            return longest_match
        
        logger.debug("No counterparty matches found")
        return None

    def identify_counterparty(self, recorder: str, description: str) -> Optional[str]:
        """
        Legacy method maintained for compatibility
        """
        return self.identify_counterparty_enhanced(recorder, description)

    def aliases_for_code(self, code: str, limit: int = 10) -> List[str]:
        for entry in self.entries:
            if entry.code == code:
                aliases = sorted(entry.alias_set, key=str.lower)
                if limit and len(aliases) > limit:
                    return aliases[:limit]
                return aliases
        return []

    def format_for_prompt(self, alias_cap: int = 8) -> str:
        lines: List[str] = []
        for entry in self.entries:
            aliases = sorted(entry.alias_set, key=str.lower)
            if alias_cap and len(aliases) > alias_cap:
                alias_text = ", ".join(aliases[:alias_cap]) + ", ..."
            else:
                alias_text = ", ".join(aliases)
            lines.append(f"{entry.code}: {alias_text}")
        return "\n".join(lines)


class SubsidiaryLedgerIdentifier:
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
        self.property_db = PropertyDatabase(self.property_sheet.get_all_values())
        self.openai = OpenAI(api_key=openai_key)
        self.model = model

    def fetch_pending_rows(self) -> List[Dict[str, str]]:
        values = self.classify_sheet.get_all_values()
        pending: List[Dict[str, str]] = []
        for idx, row in enumerate(values, start=1):
            if idx == 1:
                continue  # header row
            recorder = row[0].strip() if len(row) > 0 else ""
            description = row[8].strip() if len(row) > 8 else ""  # Column I (index 8)
            existing = row[9].strip() if len(row) > 9 else ""      # Column J (index 9)
            if not description:
                continue
            # Treat "unknown" as pending for re-processing
            if existing and existing.lower() != "unknown":
                continue
            pending.append(
                {
                    "row": idx,
                    "recorder": recorder,
                    "description": description,
                    "description_matches": sorted(self.property_db.identify_codes(description)),
                    "recorder_matches": sorted(self.property_db.identify_codes(recorder)),
                }
            )
        return pending

    def process_batches(self, batch_size: int = DEFAULT_BATCH_SIZE, max_batches: Optional[int] = None) -> None:
        pending = self.fetch_pending_rows()
        if not pending:
            logger.info("No pending rows to classify.")
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
        
        logger.info("=" * 80)
        logger.info("PROCESSING BATCH - Enhanced AI Counterparty Identification")
        logger.info("=" * 80)

        # Phase 1: Direct matching using enhanced algorithm
        logger.info("PHASE 1: Direct matching with enhanced algorithm")
        for record in batch:
            logger.info(f"Row {record['row']}: Recorder='{record['recorder']}' | Description='{record['description']}'")
            
            direct_match = self.property_db.identify_counterparty_enhanced(record["recorder"], record["description"])
            if direct_match:
                logger.info(f"✅ Row {record['row']} RESOLVED via direct matching → {direct_match}")
                updates.append({"row": record["row"], "value": direct_match})
            else:
                logger.info(f"⚠️  Row {record['row']} requires AI processing")
                unresolved.append(record)

        # Phase 2: AI processing for unresolved cases
        if unresolved:
            logger.info(f"\nPHASE 2: AI processing for {len(unresolved)} unresolved transactions")
            ai_results = self._classify_with_ai(unresolved)
            for row, value in ai_results.items():
                if value and value.lower() != "unknown":
                    logger.info(f"🤖 Row {row} AI RESOLVED → {value}")
                    updates.append({"row": row, "value": value})
                else:
                    logger.info(f"❌ Row {row} remains UNKNOWN after AI processing")
                    # Always add "unknown" to updates instead of leaving blank
                    updates.append({"row": row, "value": "unknown"})

        # Phase 3: Update Google Sheets with results
        if updates:
            logger.info(f"\nPHASE 3: Updating {len(updates)} rows in Google Sheets")
            request_body = [
                {
                    "range": f"J{item['row']}",  # Column J - Counterparty Property Code
                    "values": [[item["value"]]],
                }
                for item in updates
            ]
            self.classify_sheet.batch_update(request_body)
            logger.info("✅ Successfully updated %s rows in current batch.", len(updates))
            
            # Log summary of updates
            for item in updates:
                logger.info(f"   Row {item['row']} → {item['value']}")
        else:
            logger.warning("⚠️  No updates produced for this batch - all transactions remain unknown")
            
        logger.info("=" * 80)
        logger.info("BATCH PROCESSING COMPLETE")
        logger.info("=" * 80)

    def _classify_with_ai(self, pending: Sequence[Dict[str, str]]) -> Dict[int, str]:
        """Enhanced AI classification with detailed step-by-step algorithm"""
        
        # Normalize property database for AI processing
        normalized_property_db = []
        for entry in self.property_db.entries:
            normalized_aliases = [alias.lower() for alias in entry.alias_set]
            normalized_property_db.append({
                "code": entry.code,
                "aliases": normalized_aliases
            })
        
        # Prepare enhanced transactions with normalization
        enhanced_transactions = []
        for record in pending:
            normalized_desc = self.property_db._normalize(record["description"])
            enhanced_transactions.append({
                "row": record["row"],
                "recorder": record["recorder"].lower(),
                "description": record["description"],
                "normalized_description": normalized_desc,
                "recorder_matches": record["recorder_matches"],
                "description_matches": record["description_matches"],
            })

        prompt_payload = {
            "normalized_property_database": normalized_property_db,
            "detailed_algorithm": [
                "STEP 1: Normalize the transaction description to lowercase for consistent processing.",
                "STEP 2: Identify the recorder entity (Column A property code) and all its aliases from the normalized property database.",
                "STEP 3: Remove/filter out ALL mentions of the recorder entity and its aliases from the normalized description.",
                "STEP 4: Search the processed description against the normalized property database for any remaining property codes or aliases.",
                "STEP 5: Return ONLY the property code of the counterparty entity found, or 'unknown' if no match exists.",
                "",
                "CRITICAL RULES:",
                "- The recorder entity is NEVER the counterparty - always exclude it",
                "- Match property names, aliases, and codes from the database",
                "- Only return 'unknown' when NO counterparty can be confidently identified",
                "- Prioritize exact matches over partial matches",
                "- MSS2 references should resolve to 'ssmsouth' property code"
            ],
            "transactions": enhanced_transactions,
        }

        response = self.openai.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert accounting assistant specializing in property transaction analysis. You process data methodically following the exact algorithm provided. Output only valid JSON with no explanations."
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task": "Follow the detailed algorithm to identify counterparty property codes for each transaction. This is CRITICAL for accurate account reconciliation.",
                            "algorithm": prompt_payload["detailed_algorithm"],
                            "normalized_property_database": prompt_payload["normalized_property_database"],
                            "transactions_to_process": prompt_payload["transactions"],
                            "response_format": "Return ONLY a JSON object where keys are row numbers (as strings) and values are property codes or 'unknown'. No other text."
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,  # Deterministic output for consistency
        )

        output_text = response.choices[0].message.content.strip()
        logger.info(f"🤖 AI raw response: {output_text}")

        # Enhanced parsing to handle various AI response formats
        if output_text.startswith("```json"):
            output_text = output_text[7:]  # Remove ```json
        elif output_text.startswith("```"):
            output_text = output_text[3:]   # Remove ```
        if output_text.endswith("```"):
            output_text = output_text[:-3]  # Remove trailing ```
        output_text = output_text.strip()

        # Remove any leading/trailing explanatory text that might be present
        json_start = output_text.find('{')
        json_end = output_text.rfind('}')
        if json_start != -1 and json_end != -1 and json_end > json_start:
            output_text = output_text[json_start:json_end + 1]

        try:
            result_map = json.loads(output_text)
            logger.info(f"✅ Successfully parsed AI response: {result_map}")
        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse AI response: {e}")
            logger.error(f"Raw response: {output_text}")
            return {record["row"]: "unknown" for record in pending}

        # Enhanced result processing with validation
        parsed: Dict[int, str] = {}
        for record in pending:
            key = str(record["row"])
            value = result_map.get(key, "").strip()
            
            # Validate the returned value
            if not value or value.lower() in ["", "none", "null"]:
                parsed[record["row"]] = "unknown"
                logger.warning(f"Row {record['row']}: AI returned empty/null value, marking as unknown")
            elif value.lower() == "unknown":
                parsed[record["row"]] = "unknown"
                logger.info(f"Row {record['row']}: AI determined counterparty is unknown")
            else:
                # Validate that the returned code exists in the property database
                valid_codes = {entry.code for entry in self.property_db.entries}
                if value in valid_codes:
                    parsed[record["row"]] = value
                    logger.info(f"Row {record['row']}: AI identified valid counterparty → {value}")
                else:
                    parsed[record["row"]] = "unknown"
                    logger.warning(f"Row {record['row']}: AI returned invalid property code '{value}', marking as unknown")
                    
        return parsed


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Identify counterparty property codes in Google Sheets.")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="Target Google Sheet ID (default: provided ID)")
    parser.add_argument("--service-account", default=None, help="Override path to the Google service account JSON file")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Number of rows to process per batch (default: 25)")
    parser.add_argument("--max-batches", type=int, default=None, help="Optional limit on number of batches to process")
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

    identifier = SubsidiaryLedgerIdentifier(
        sheet_id=args.sheet_id,
        service_account_path=service_account_path,
        openai_key=openai_key,
        model=args.model,
    )

    identifier.process_batches(batch_size=args.batch_size, max_batches=args.max_batches)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error while identifying subsidiary ledger: %s", exc)
        sys.exit(1)
