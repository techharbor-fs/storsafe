"""
Notre Dame Federal Credit Union Bank Statement Parser

Parses transaction data from Notre Dame FCU bank statement PDFs.
Based on format analysis of "--- SS of Madison_Notre Dame 11.30.2025.pdf"
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .base_parser import BaseBankParser, Transaction


class NotreDameFCUParser(BaseBankParser):
    """Parser for Notre Dame Federal Credit Union bank statements."""
    
    BANK_NAME = "Notre Dame Federal Credit Union"
    
    # Account suffix we're interested in (160 = OPERATING account)
    TARGET_ACCOUNT_SUFFIX = "160"
    
    def __init__(self):
        super().__init__()
        self.property_name = None
    
    @classmethod
    def can_parse(cls, pdf_path: Path, text_content: str) -> bool:
        """Check if this is a Notre Dame FCU statement."""
        # PDF may contain "NotreDameFCU" (no spaces) or with non-breaking spaces
        text_normalized = text_content.replace('\xa0', ' ').upper()
        return "NOTREDAMEFCU" in text_content or "NOTRE DAME" in text_normalized
    
    def _extract_property_name(self, pdf_path: Path, text: str) -> Optional[str]:
        """
        Extract property name from filename or content.
        
        Filename patterns:
        - "--- SS of Madison_Notre Dame 11.30.2025.pdf" -> "Madison"
        - "SS of Chicago Notre Dame 12.31.2025.pdf" -> "Chicago"
        """
        filename = pdf_path.name
        
        # Pattern: "SS of {Property}_" or "SS of {Property} "
        match = re.search(r'SS\s+of\s+([A-Za-z]+)[\s_]', filename, re.IGNORECASE)
        if match:
            return match.group(1).title()
        
        # Try content - look for "SS OF MADISON" pattern in text
        match = re.search(r'SS\s+OF\s+([A-Z]+)', text.upper())
        if match:
            return match.group(1).title()
        
        return None
    
    def parse(self, pdf_path: Path) -> List[Transaction]:
        """Parse transactions from Notre Dame FCU statement."""
        text = self.extract_pdf_text(pdf_path)
        # Normalize non-breaking spaces to regular spaces
        text = text.replace('\xa0', ' ')
        
        # Extract property name
        self.property_name = self._extract_property_name(pdf_path, text)
        
        return self._parse_transactions(text)
    
    def _parse_transactions(self, text: str) -> List[Transaction]:
        """
        Extract transactions from the text content.
        
        Notre Dame FCU format is multi-line:
        - Date line: "11/07/25"
        - Transaction type: "CHECK 07385325" or "ACH/MerchPayout SV9T"
        - Check/ID: "1100"
        - Transfer account (optional)
        - Amount: "$2,056.66­" (with minus sign) or "$290.00 "
        - Balance
        """
        transactions = []
        lines = text.split('\n')
        
        in_operating_section = False
        i = 0
        
        while i < len(lines):
            line = lines[i].strip()
            
            # Detect start of 160: OPERATING section
            if "160:" in line and ("OPERATING" in line or "ULTIMATE BUSINESS" in line):
                in_operating_section = True
                i += 1
                continue
            
            # Detect end of section (next numbered account or loan section)
            if in_operating_section:
                if re.match(r'^\d{3}:', line) or "LOAN ACCOUNTS" in line:
                    in_operating_section = False
                    i += 1
                    continue
            
            if not in_operating_section:
                i += 1
                continue
            
            # Skip non-transaction lines
            if "Beginning Balance" in line or "Ending Balance" in line:
                i += 1
                continue
                
            # Skip headers and summary lines
            if line in ("Date", "Transaction Type", "#/ID", "Transfer Acct", 
                       "Deposit Withdrawal", "Balance", "Deposit", "Withdrawal"):
                i += 1
                continue
            
            # Look for date pattern (MM/DD/YY)
            date_match = re.match(r'^(\d{2}/\d{2}/\d{2})$', line)
            if date_match:
                # We found a date - now parse the following lines for transaction details
                trans = self._parse_transaction_block(lines, i)
                if trans:
                    transactions.append(trans)
            
            i += 1
        
        return transactions
    
    def _parse_transaction_block(self, lines: List[str], date_idx: int) -> Optional[Transaction]:
        """
        Parse a transaction block starting at the date line.
        
        The format is approximately:
        [date_idx]     "11/07/25"
        [date_idx+1]   "CHECK 07385325" or "ACH/MerchPayout SV9T"
        [date_idx+2]   Check number or ID: "1100"
        [date_idx+3...]  Amount and balance info
        """
        try:
            date_str = lines[date_idx].strip()
            month, day, year_short = date_str.split('/')
            trans_date = datetime(2000 + int(year_short), int(month), int(day))

            # Capture the raw statement values to map to sheet columns
            # Requirement:
            # - Transaction type -> Description
            # - #/ID -> Transaction ID (blank if statement has none)
            statement_type: str = ""
            statement_id: str = ""

            # Look at next several lines to gather transaction info
            block_lines: List[str] = []
            for j in range(date_idx + 1, min(date_idx + 10, len(lines))):
                nxt = lines[j].strip()
                if not nxt:
                    continue
                # Stop if we hit another date or section marker
                if re.match(r'^\d{2}/\d{2}/\d{2}$', nxt):
                    break
                if "** " in nxt or nxt.startswith("Year"):
                    break
                block_lines.append(nxt)

            # First non-numeric/non-amount line is the transaction type
            for bl in block_lines:
                # Skip pure dollar lines
                if "$" in bl:
                    continue
                # Skip pure numeric lines (these are typically #/ID)
                if re.fullmatch(r'\d+', bl):
                    continue
                statement_type = bl
                break

            # Collect any continuation lines that visually belong under "Transaction Type".
            # Key requirement from user:
            # - Transaction ID should ONLY reflect the statement's #/ID column.
            #   In this statement, CHECK rows have a #/ID (e.g., 1089) but ACH/MerchPayout
            #   rows typically do not; the trailing 10-digit number (e.g., 8662240369)
            #   is displayed under Transaction Type and should remain in Description.
            continuation_lines: List[str] = []

            type_idx = -1
            if statement_type:
                type_idx = next((k for k, v in enumerate(block_lines) if v == statement_type), -1)

            statement_type_upper = statement_type.upper() if statement_type else ""

            # Parse subsequent lines after the type.
            for bl in (block_lines[type_idx + 1:] if type_idx >= 0 else block_lines):
                # Skip anything that looks like an amount/balance artifact
                if "$" in bl:
                    continue

                if re.fullmatch(r'\d+', bl):
                    # CHECK rows: the next numeric-only line is the statement #/ID.
                    if statement_type_upper.startswith("CHECK") and not statement_id:
                        statement_id = bl
                        continue

                    # Non-CHECK rows: numeric-only lines are part of the Transaction Type cell.
                    continuation_lines.append(bl)
                    continue

                continuation_lines.append(bl)

            # Derive a lightweight normalized transaction_type (optional field)
            trans_type_upper = statement_type_upper
            if trans_type_upper.startswith("CHECK"):
                trans_type = "CHECK"
            elif trans_type_upper.startswith("ACH/"):
                trans_type = "ACH"
            elif "FEE" in trans_type_upper:
                trans_type = "FEE"
            elif "TRANSFER" in trans_type_upper:
                trans_type = "TRANSFER"
            elif statement_type:
                trans_type = "OTHER"
            else:
                trans_type = "OTHER"
            
            # Fix: Use en-dash character and regular dash for negative amounts
            # The PDF uses "­" which is a soft hyphen (U+00AD)
            block_text = " ".join(block_lines)
            block_text_normalized = block_text.replace('\xad', '-').replace('­', '-')
            
            # Extract amount - look for $X,XXX.XX patterns
            # Find all dollar amounts
            amounts = re.findall(r'\$([0-9,]+\.\d{2})(\-)?', block_text_normalized)
            
            if not amounts:
                return None
                
            # Usually the first amount in the block is the transaction amount
            # (subsequent ones are balances)
            amount_str, negative_sign = amounts[0]
            amount = float(amount_str.replace(',', ''))
            
            if negative_sign == '-':
                amount = -amount
            
            # Map statement Transaction Type cell directly to sheet Description (multi-line)
            description_lines = [statement_type] if statement_type else []
            description_lines.extend([c for c in continuation_lines if c])
            description = "\n".join(description_lines).strip()
            
            return Transaction(
                date=trans_date,
                # Only show Transaction ID when statement provides it; otherwise blank
                transaction_id=statement_id if statement_type_upper.startswith("CHECK") else "",
                description=description,
                amount=amount,
                transaction_type=trans_type,
                check_number=statement_id if trans_type == "CHECK" and statement_id else None
            )
            
        except Exception as e:
            return None
