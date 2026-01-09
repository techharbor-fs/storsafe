"""
Base Bank Statement Parser

Abstract base class for parsing different bank statement formats.
Each bank gets its own parser implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


@dataclass
class Transaction:
    """Represents a single bank transaction."""
    date: datetime
    transaction_id: str
    description: str
    amount: float  # Positive = deposit/credit, Negative = withdrawal/debit
    transaction_type: str = ""  # e.g., "CHECK", "ACH", "DEPOSIT"
    check_number: Optional[str] = None
    
    def to_sheet_row(self, property_name: str) -> List:
        """Convert to Google Sheet row format: [Property, Date, Transaction ID, Description, Amount]"""
        return [
            property_name,
            self.date.strftime("%m/%d/%Y"),
            self.transaction_id,
            self.description,
            self.amount
        ]


class BaseBankParser(ABC):
    """Abstract base class for bank statement parsers."""
    
    # Subclasses should define this to identify which bank they handle
    BANK_NAME: str = "Unknown"
    
    @classmethod
    @abstractmethod
    def can_parse(cls, pdf_path: Path, text_content: str) -> bool:
        """
        Check if this parser can handle the given PDF.
        
        Args:
            pdf_path: Path to the PDF file
            text_content: Extracted text from PDF (first few pages)
            
        Returns:
            True if this parser can handle this bank statement
        """
        pass
    
    @abstractmethod
    def parse(self, pdf_path: Path) -> List[Transaction]:
        """
        Parse the bank statement PDF and extract transactions.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of Transaction objects
        """
        pass
    
    @staticmethod
    def extract_pdf_text(pdf_path: Path) -> str:
        """Extract text content from PDF using PyMuPDF blocks mode."""
        import fitz
        
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            # Use 'blocks' mode to get proper line breaks
            blocks = page.get_text('blocks')
            for block in blocks:
                if block[6] == 0:  # Text block (not image)
                    text += block[4]
        doc.close()
        return text
