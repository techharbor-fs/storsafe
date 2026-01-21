"""Bank Parsers Package"""

from .base_parser import BaseBankParser, Transaction
from .notre_dame_fcu import NotreDameFCUParser

# Registry of all available parsers
PARSERS = [
    NotreDameFCUParser,
]


def get_parser_for_pdf(pdf_path):
    """
    Find the appropriate parser for a given PDF.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Parser instance if found, None otherwise
    """
    from pathlib import Path
    
    pdf_path = Path(pdf_path)
    text = BaseBankParser.extract_pdf_text(pdf_path)
    
    for parser_class in PARSERS:
        if parser_class.can_parse(pdf_path, text):
            return parser_class()
    
    return None


__all__ = ['BaseBankParser', 'Transaction', 'NotreDameFCUParser', 'get_parser_for_pdf', 'PARSERS']
