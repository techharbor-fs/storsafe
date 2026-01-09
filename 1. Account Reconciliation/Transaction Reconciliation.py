#!/usr/bin/env python3
"""
Transaction Reconciliation Script

This script reconciles transactions through a complete 3-phase pipeline by default.
Matched pairs are written to "Matched" sheet, and unmatched rows are written to "Unmatched" sheet.

Column Structure:
- Column L (index 11): Credit transactions (intercompany matching values)
- Column M (index 12): Debit transactions (intercompany matching values)  

Complete Pipeline Process:
Phase 1: Direct Column L ↔ Column M matching (exact string comparison)
Phase 2: Subsidiary ledger balance elimination (balanced groups to "Matched")
Phase 3: Intercompany transaction matching (entity swap detection)

All phases append results with proper labeling in Column Q for audit trail.

Usage Examples:
- Run complete pipeline: python "Transaction Reconciler.py"
- Run Phase 1 only: python "Transaction Reconciler.py" --phase1-only
- Skip Phase 2: python "Transaction Reconciler.py" --no-phase2
- Skip Phase 3: python "Transaction Reconciler.py" --no-phase3
- Custom sheet: python "Transaction Reconciler.py" --sheet-id YOUR_SHEET_ID
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import tempfile
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from typing import Dict, List, Optional, Set, Tuple

import gspread
import keyboard

# Configuration
DEFAULT_SHEET_ID = "1LKwP5e61ci10mtQm3MytN8_WuPgxcm2R-L6hB003zoY"
SOURCE_SHEET_NAME = "Due To/From GL - 08.31.25"
MATCHED_SHEET_NAME = "Matched"
UNMATCHED_SHEET_NAME = "Unmatched"

# Phase 4 Configuration
PHASE4_THRESHOLD = 10000  # Minimum amount for suggestive matching
PHASE4_HOTKEY_PROCESS = 'f10'  # Process matched pairs

logger = logging.getLogger(__name__)


def date_to_serial(date_value):
    """
    Convert date to Google Sheets serial number.
    
    Google Sheets stores dates as serial numbers (days since December 30, 1899).
    This is the ONLY guaranteed method to ensure dates are stored as DATE type.
    
    Args:
        date_value: Date in various formats (string, datetime, date, or already a number)
    
    Returns:
        int: Serial number (days since Dec 30, 1899), or original value if conversion fails
    
    Examples:
        >>> date_to_serial("01/15/2024")
        45306
        >>> date_to_serial("2024-01-15")
        45306
    """
    from datetime import datetime, date
    
    # If already a number, return as-is
    if isinstance(date_value, (int, float)):
        return date_value
    
    # If None or empty, return as-is
    if not date_value:
        return date_value
    
    # Google Sheets epoch: December 30, 1899
    epoch = datetime(1899, 12, 30).date()
    
    # Handle string input - try common formats
    if isinstance(date_value, str):
        date_value = date_value.strip()
        
        # List of common date formats to try
        date_formats = [
            '%m/%d/%Y',    # 01/15/2024
            '%Y-%m-%d',    # 2024-01-15
            '%m-%d-%Y',    # 01-15-2024
            '%d/%m/%Y',    # 15/01/2024
            '%Y/%m/%d',    # 2024/01/15
            '%m/%d/%y',    # 01/15/24
            '%d-%m-%Y',    # 15-01-2024
            '%B %d, %Y',   # January 15, 2024
            '%b %d, %Y',   # Jan 15, 2024
        ]
        
        for fmt in date_formats:
            try:
                date_value = datetime.strptime(date_value, fmt).date()
                break
            except ValueError:
                continue
        else:
            # No format matched - return original value
            return date_value
    
    # Convert datetime to date
    if isinstance(date_value, datetime):
        date_value = date_value.date()
    
    # Calculate days since epoch
    if isinstance(date_value, date):
        delta = date_value - epoch
        return delta.days
    
    # If we got here, we couldn't convert - return original
    return date_value


def batch_format_columns(sheet, date_ranges: List[str] = None, date_mmyyyy_ranges: List[str] = None, 
                         text_ranges: List[str] = None, number_ranges: Dict[str, str] = None):
    """
    Batch all column formatting into a single API request to avoid rate limits.
    
    Args:
        sheet: gspread Worksheet object
        date_ranges: List of ranges to format as dates (mm/dd/yyyy)
        date_mmyyyy_ranges: List of ranges to format as dates (mm-yyyy)
        text_ranges: List of ranges to format as plain text
        number_ranges: Dict of {range: pattern} for number formatting
    
    Example:
        batch_format_columns(
            sheet,
            date_ranges=['B2:B100'],
            date_mmyyyy_ranges=['C2:C100'],
            text_ranges=['E2:E100'],
            number_ranges={'F2:F100': '#,##0.00', 'G2:G100': '#,##0.00'}
        )
    """
    formats = []
    
    # Add date formats (mm/dd/yyyy)
    if date_ranges:
        for range_name in date_ranges:
            formats.append({
                'range': range_name,
                'format': {
                    "numberFormat": {
                        "type": "DATE",
                        "pattern": "mm/dd/yyyy"
                    }
                }
            })
    
    # Add date formats (mm-yyyy)
    if date_mmyyyy_ranges:
        for range_name in date_mmyyyy_ranges:
            formats.append({
                'range': range_name,
                'format': {
                    "numberFormat": {
                        "type": "DATE",
                        "pattern": "mm-yyyy"
                    }
                }
            })
    
    # Add text formats
    if text_ranges:
        for range_name in text_ranges:
            formats.append({
                'range': range_name,
                'format': {
                    "numberFormat": {
                        "type": "TEXT"
                    }
                }
            })
    
    # Add number formats
    if number_ranges:
        for range_name, pattern in number_ranges.items():
            formats.append({
                'range': range_name,
                'format': {
                    "numberFormat": {
                        "type": "NUMBER",
                        "pattern": pattern
                    }
                }
            })
    
    # Apply all formats in a single batch request
    if formats:
        sheet.batch_format(formats)


def format_date_columns(sheet, ranges: List[str], pattern: str = "mm/dd/yyyy"):
    """
    Apply DATE formatting to specified column ranges.
    
    This ensures columns are displayed as dates in Google Sheets,
    with the calendar icon indicator.
    
    Args:
        sheet: gspread Worksheet object
        ranges: List of A1 notation ranges, e.g., ['B2:B', 'E2:E100']
        pattern: Date format pattern (default: "mm/dd/yyyy" - with leading zeros)
    """
    date_format = {
        "numberFormat": {
            "type": "DATE",
            "pattern": pattern
        }
    }
    
    for range_name in ranges:
        sheet.format(range_name, date_format)


def format_number_columns(sheet, column_formats: Dict[str, str]):
    """
    Apply NUMBER formatting to specified column ranges.
    
    This ensures columns are displayed as numbers in Google Sheets,
    with proper numeric formatting (e.g., #,##0.00 for currency).
    
    Args:
        sheet: gspread Worksheet object
        column_formats: Dict mapping A1 notation ranges to format patterns
                       Example: {'C2:C': '#,##0.00', 'F2:F': '#,##0.00'}
                       
    Common patterns:
        - '#,##0.00' = Number with 2 decimals and thousands separator (1,000.00)
        - '#,##0' = Integer with thousands separator (1,000)
        - '0.00' = Decimal without thousands separator (1000.00)
    """
    for range_name, pattern in column_formats.items():
        number_format = {
            "numberFormat": {
                "type": "NUMBER",
                "pattern": pattern
            }
        }
        sheet.format(range_name, number_format)


def format_text_columns(sheet, ranges: List[str]):
    """
    Apply TEXT (plain text) formatting to specified column ranges.
    
    This prevents Google Sheets from auto-converting values to numbers
    and ensures columns remain as plain text strings.
    
    Args:
        sheet: gspread Worksheet object
        ranges: List of A1 notation ranges, e.g., ['E2:E', 'H2:H100']
    """
    text_format = {
        "numberFormat": {
            "type": "TEXT"
        }
    }
    
    for range_name in ranges:
        sheet.format(range_name, text_format)


def convert_column_b_to_serial(rows: List[List]) -> List[List]:
    """
    Convert Column B (index 1) dates to serial numbers.
    
    This ensures dates are stored as DATE type in Google Sheets, not TEXT.
    
    Args:
        rows: List of row data (including header)
    
    Returns:
        List of rows with Column B converted to serial numbers
    """
    if not rows:
        return rows
    
    processed_rows = []
    
    for i, row in enumerate(rows):
        if i == 0:  # Skip header row
            processed_rows.append(row)
            continue
        
        # Create a copy of the row
        new_row = row.copy()
        
        # Convert Column B (index 1) to serial number if it exists
        if len(new_row) > 1 and new_row[1]:
            new_row[1] = date_to_serial(new_row[1])
        
        processed_rows.append(new_row)
    
    return processed_rows


def generate_distinct_colors(count: int = 50) -> List[Dict[str, float]]:
    """
    Generate visually distinct colors with black text visibility.
    Returns list of color dicts in Google Sheets API format.
    """
    colors = []
    
    # Generate colors using HSV color space for maximum distinctiveness
    # Keep saturation and value high enough for black text visibility
    import colorsys
    
    for i in range(count):
        # Distribute hues evenly across color spectrum
        hue = i / count
        
        # Use moderate saturation and high value for pastels (good with black text)
        saturation = 0.45 + (i % 3) * 0.15  # 0.45, 0.60, 0.75
        value = 0.85 + (i % 2) * 0.1  # 0.85, 0.95
        
        # Convert HSV to RGB
        r, g, b = colorsys.hsv_to_rgb(hue, saturation, value)
        
        # Google Sheets API color format (values 0-1)
        colors.append({
            "red": r,
            "green": g,
            "blue": b
        })
    
    return colors


def safe_str(value) -> str:
    """
    Safely convert a value to string, handling None, numbers, and strings.
    
    Args:
        value: Any value (string, number, None, etc.)
    
    Returns:
        String representation of the value, or empty string if None/empty
    """
    if value is None or value == '':
        return ''
    if isinstance(value, str):
        return value.strip()
    # Convert numbers and other types to string
    return str(value).strip()


class TransactionReconciler:
    def __init__(self, sheet_id: str, service_account_path: Path, run_phase2: bool = True, run_phase3: bool = True, run_phase4: bool = True):
        self.sheet_id = sheet_id
        self.client = gspread.service_account(filename=str(service_account_path))
        self.workbook = self.client.open_by_key(sheet_id)
        self.source_sheet = self.workbook.worksheet(SOURCE_SHEET_NAME)
        self.run_phase2 = run_phase2
        self.run_phase3 = run_phase3
        self.run_phase4 = run_phase4
        
        # Phase 4 state
        self.phase4_colors = generate_distinct_colors(50)
        self.phase4_color_index = 0
        self.phase4_used_colors = set()
        self.phase4_running = False
        
        # Phase 4 column J/K tracking for change detection
        # Structure: {unique_id (Column P): {'J': value, 'K': value}}
        self.phase4_original_matched_jk = {}
        self.phase4_original_unmatched_jk = {}

    def reconcile_transactions(self) -> None:
        """Transaction reconciliation with Column L ↔ Column M matching"""
        logger.info("Starting transaction reconciliation...")
        
        logger.info(f"=" * 60)
        logger.info(f"🔄 TRANSACTION RECONCILIATION")
        logger.info(f"=" * 60)
        
        self._run_phase1()
        
        # Run Phase 2 if requested
        if self.run_phase2:
            self._run_phase2()
            
        # Run Phase 3 if requested
        if self.run_phase3:
            self._run_phase3()
        
        # Run Phase 4 if requested
        if self.run_phase4:
            self._run_phase4()
        
        logger.info("✅ Transaction reconciliation completed!")

    def _run_phase1(self) -> None:
        """Phase 1: Direct Column L ↔ Column M matching across all rows"""
        logger.info("Phase 1: Column L ↔ Column M direct matching")
        
        # Get all data from source sheet (use UNFORMATTED_VALUE to preserve number types)
        source_data = self.source_sheet.get(value_render_option='UNFORMATTED_VALUE')
        if len(source_data) <= 1:
            logger.info("No data to reconcile.")
            return
        
        logger.info(f"📋 Processing {len(source_data) - 1} data rows")
        
        # Clear existing data in output sheets (Phase 1 is the start of reconciliation)
        self._clear_output_sheets()
        
        # Find matching pairs between Column L (index 11) and Column M (index 12)
        matched_pairs = self._find_matching_pairs(source_data)
        logger.info(f"Found {len(matched_pairs)} exact matching pairs")
        
        # Identify unmatched rows
        unmatched_rows = self._identify_unmatched_rows(source_data, matched_pairs)
        logger.info(f"Found {len(unmatched_rows)} unmatched transactions")
        
        # Write matched pairs to "Matched" sheet
        self._write_matched_pairs_to_sheet(source_data, matched_pairs, "Phase 1")
        
        # Write unmatched transactions to "Unmatched" sheet
        self._write_unmatched_to_sheet(source_data, unmatched_rows)
        
        logger.info("📊 Phase 1 complete - transactions separated into 'Matched' and 'Unmatched' sheets")

    def _run_phase2(self) -> None:
        """Phase 2: Eliminate balanced subsidiary ledgers from 'Unmatched' sheet"""
        logger.info("Phase 2: Subsidiary ledger balance elimination")
        
        # Get data from "Unmatched" sheet (use UNFORMATTED_VALUE to preserve number types)
        try:
            unmatched_sheet = self.workbook.worksheet("Unmatched")
            unmatched_data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
        except Exception as e:
            logger.error(f"Could not access 'Unmatched' sheet: {e}")
            return
        
        if len(unmatched_data) <= 1:
            logger.info("No data in 'Unmatched' sheet to process")
            return
        
        original_unmatched_count = len(unmatched_data) - 1  # Store original count for comparison
        logger.info(f"📋 Processing {original_unmatched_count} transactions from 'Unmatched' sheet")
        
        # Group transactions by subsidiary ledger (Column N, index 13)
        subsidiary_groups = {}
        header_row = unmatched_data[0]
        
        for i, row in enumerate(unmatched_data[1:], 1):  # Skip header
            if len(row) > 13:
                subsidiary_ledger = safe_str(row[13]) if safe_str(row[13]) else "unknown"
                
                if subsidiary_ledger not in subsidiary_groups:
                    subsidiary_groups[subsidiary_ledger] = {
                        'rows': [],
                        'total_debit': 0.0,
                        'total_credit': 0.0
                    }
                
                # Add row to group (ensure A-P columns)
                row_ap = row[:16] if len(row) >= 16 else row
                subsidiary_groups[subsidiary_ledger]['rows'].append(row_ap)
                
                # Sum Column F (debit) and Column G (credit)
                debit_amount = 0.0
                credit_amount = 0.0
                
                # Handle both numeric (from UNFORMATTED_VALUE) and string values
                if len(row) > 5 and row[5]:
                    try:
                        # If already a number, use it directly
                        if isinstance(row[5], (int, float)):
                            debit_amount = float(row[5])
                        # If string, parse it
                        elif isinstance(row[5], str):
                            debit_str = row[5].strip().replace(',', '').replace('$', '')
                            if debit_str:
                                debit_amount = float(debit_str)
                    except (ValueError, TypeError):
                        debit_amount = 0.0
                
                if len(row) > 6 and row[6]:
                    try:
                        # If already a number, use it directly
                        if isinstance(row[6], (int, float)):
                            credit_amount = float(row[6])
                        # If string, parse it
                        elif isinstance(row[6], str):
                            credit_str = row[6].strip().replace(',', '').replace('$', '')
                            if credit_str:
                                credit_amount = float(credit_str)
                    except (ValueError, TypeError):
                        credit_amount = 0.0
                
                subsidiary_groups[subsidiary_ledger]['total_debit'] += debit_amount
                subsidiary_groups[subsidiary_ledger]['total_credit'] += credit_amount
        
        logger.info(f"📊 Found {len(subsidiary_groups)} subsidiary ledgers to analyze")
        
        # Identify balanced vs unbalanced subsidiaries
        balanced_subsidiaries = []
        unbalanced_subsidiaries = []
        
        for subsidiary, data in subsidiary_groups.items():
            net_balance = data['total_debit'] - data['total_credit']
            
            if abs(net_balance) < 0.01:  # Consider amounts within 1 cent as balanced
                balanced_subsidiaries.append({
                    'name': subsidiary,
                    'debit': data['total_debit'],
                    'credit': data['total_credit'],
                    'net': net_balance,
                    'rows': data['rows']
                })
            else:
                unbalanced_subsidiaries.append({
                    'name': subsidiary,
                    'debit': data['total_debit'],
                    'credit': data['total_credit'],
                    'net': net_balance,
                    'rows': data['rows']
                })
        
        # Log analysis results
        balanced_count = sum(len(sub['rows']) for sub in balanced_subsidiaries)
        unbalanced_count = sum(len(sub['rows']) for sub in unbalanced_subsidiaries)
        
        logger.info(f"🟢 Balanced subsidiaries (to move to 'Matched'): {len(balanced_subsidiaries)} groups, {balanced_count} transactions")
        for sub in balanced_subsidiaries:
            logger.info(f"  • {sub['name']}: {len(sub['rows'])} rows, Debit: ${sub['debit']:.2f}, Credit: ${sub['credit']:.2f}, Net: ${sub['net']:.2f}")
        
        logger.info(f"🔴 Unbalanced subsidiaries (to remain 'Unmatched'): {len(unbalanced_subsidiaries)} groups, {unbalanced_count} transactions")
        for sub in unbalanced_subsidiaries:
            logger.info(f"  • {sub['name']}: {len(sub['rows'])} rows, Debit: ${sub['debit']:.2f}, Credit: ${sub['credit']:.2f}, Net: ${sub['net']:.2f}")
        
        # Append balanced subsidiaries to "Matched" sheet
        if balanced_subsidiaries:
            self._append_balanced_to_matched(balanced_subsidiaries)
        
        # Update "Unmatched" sheet if transactions were removed
        if balanced_count > 0:  # Some transactions were balanced and moved
            self._update_unmatched_with_remaining(header_row, unbalanced_subsidiaries, original_unmatched_count)
        else:
            logger.info("  📋 No balanced subsidiaries found - 'Unmatched' sheet remains unchanged")
        
        # Summary
        logger.info(f"📊 Phase 2 complete:")
        logger.info(f"  • Moved {balanced_count} transactions from {len(balanced_subsidiaries)} balanced subsidiaries to 'Matched'")
        logger.info(f"  • Retained {unbalanced_count} transactions from {len(unbalanced_subsidiaries)} unbalanced subsidiaries in 'Unmatched'")

    def _run_phase3(self):
        """
        Phase 3: Find intercompany transaction pairs by swapping entity positions
        
        Logic: Match transactions where "entity1-entity2-amount" (credit) pairs with "entity2-entity1-amount" (debit)
        Example: "cpwest-sscedarl-3000" should match "sscedarl-cpwest-3000"
        
        Input: "Unmatched" sheet (unmatched transactions from Phase 1/2)
        Output: Append matched pairs to "Matched" sheet, update "Unmatched" with remaining transactions
        """
        logger.info("🔄 Phase 3: Starting intercompany transaction matching...")
        
        # Initialize variables for proper scope
        matched_pairs = set()
        matched_rows = []
        unmatched_rows = []
        
        try:
            # Read data from Unmatched sheet (use UNFORMATTED_VALUE to preserve number types)
            unmatched_sheet = self.workbook.worksheet("Unmatched")
            data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
            
            if not data:
                logger.warning("No data found in Unmatched sheet")
                return
                
            header_row = data[0]
            data_rows = data[1:]
            logger.info(f"Processing {len(data_rows)} transactions for intercompany matching")
            
            # Build intercompany matching using corrected logic
            # Credit transactions: Keep original format "entity1 - entity2 - amount" 
            # Debit transactions: Use original format "entity1 - entity2 - amount"
            # Match: Credit "sscedarl - cpwest - X" with Debit "cpwest - sscedarl - X"
            credit_transactions = {}  # Maps original transaction -> [row_indices] (supports duplicates)
            debit_transactions = {}   # Maps original transaction -> [row_indices] (supports duplicates)
            matched_pairs = set()
            
            for i, row in enumerate(data_rows):
                if len(row) < 16:  # Ensure we have columns A-P
                    continue
                    
                # Get Column L (credit) and Column M (debit) values
                col_l_str = safe_str(row[11]) if len(row) > 11 else ""  # Column L (credit)
                col_m_str = safe_str(row[12]) if len(row) > 12 else ""  # Column M (debit)
                
                # Parse Column L (credit) transactions - keep original format, store multiple rows
                if col_l_str and col_l_str != "0" and " - " in col_l_str:
                    if col_l_str not in credit_transactions:
                        credit_transactions[col_l_str] = []
                    credit_transactions[col_l_str].append(i)
                
                # Parse Column M (debit) transactions - keep original format, store multiple rows
                if col_m_str and col_m_str != "0" and " - " in col_m_str:
                    if col_m_str not in debit_transactions:
                        debit_transactions[col_m_str] = []
                    debit_transactions[col_m_str].append(i)
            
            # Create intercompany matching
            # For each credit "entity1 - entity2 - amount", look for debit "entity2 - entity1 - amount"
            logger.info(f"🔍 Starting intercompany matching with {len(credit_transactions)} credits and {len(debit_transactions)} debits")
            
            # Match intercompany transactions (handle multiple rows per key)
            used_debit_rows = set()  # Track which debit rows have been matched
            
            for credit_key, credit_rows in credit_transactions.items():
                parts = credit_key.split(" - ")
                if len(parts) >= 3:
                    entity1, entity2, amount = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    # Look for the reverse: "entity2 - entity1 - amount"
                    reverse_key = f"{entity2} - {entity1} - {amount}"
                    
                    if reverse_key in debit_transactions:
                        debit_rows = debit_transactions[reverse_key]
                        
                        # Match credit rows with available debit rows (one-to-one pairing)
                        for credit_row in credit_rows:
                            for debit_row in debit_rows:
                                if debit_row not in used_debit_rows:
                                    matched_pairs.add((min(credit_row, debit_row), max(credit_row, debit_row)))
                                    used_debit_rows.add(debit_row)
                                    logger.info(f"✅ Intercompany match: Credit '{credit_key}' ↔ Debit '{reverse_key}' (rows {credit_row} ↔ {debit_row})")
                                    break  # Move to next credit row after finding a match
            
            logger.info(f"🔍 Matching complete. Found {len(matched_pairs)} total matches")
            logger.info(f"Processed: {len(credit_transactions)} credits, {len(debit_transactions)} debits")
            
            # Organize matched pairs: stack by original row order (lower row number first)
            matched_row_indices = set()
            matched_rows = []
            
            for pair in sorted(matched_pairs):  # Sort pairs to ensure consistent processing
                row1_idx, row2_idx = pair  # pair is already (min, max) from matching logic
                matched_row_indices.update(pair)
                
                # Get the two rows (ensure A-P columns)
                row1 = data_rows[row1_idx][:16] if len(data_rows[row1_idx]) >= 16 else data_rows[row1_idx]
                row2 = data_rows[row2_idx][:16] if len(data_rows[row2_idx]) >= 16 else data_rows[row2_idx]
                
                # Stack by original row order: lower row number first, then higher row number
                matched_rows.extend([row1, row2])  # row1_idx < row2_idx due to (min, max) pairing
                
            # Collect remaining unmatched rows (ensure A-P columns)
            unmatched_rows = []
            for i in range(len(data_rows)):
                if i not in matched_row_indices:
                    row = data_rows[i][:16] if len(data_rows[i]) >= 16 else data_rows[i]
                    unmatched_rows.append(row)
            
            logger.info(f"Found {len(matched_pairs)} intercompany pairs ({len(matched_rows)} transactions)")
            logger.info(f"Remaining unmatched: {len(unmatched_rows)} transactions")
            
            # Append matched transactions to "Matched" sheet (don't clear existing data)
            if matched_rows:
                # Add Phase 3 labels to matched transactions
                matched_with_labels = []
                for row in matched_rows:
                    matched_with_labels.append(row + ["Phase 3"])
                
                # Process rows to format Column B dates
                matched_with_labels = convert_column_b_to_serial([["Header"]] + matched_with_labels)[1:]  # Skip fake header
                
                # Append to existing "Matched" sheet
                try:
                    matched_sheet = self.workbook.worksheet("Matched")
                    existing_data = matched_sheet.get(value_render_option='UNFORMATTED_VALUE')
                    next_row = len(existing_data) + 1
                    
                    # Calculate range for appending
                    start_range = f"A{next_row}"
                    end_col = chr(65 + len(matched_with_labels[0]) - 1)  # A-P + Q
                    end_range = f"{end_col}{next_row + len(matched_with_labels) - 1}"
                    
                    matched_sheet.update(
                        values=matched_with_labels,
                        range_name=f"{start_range}:{end_range}",
                        value_input_option='RAW'
                    )
                    
                    # Batch format all columns in a single API call
                    batch_format_columns(
                        matched_sheet,
                        date_ranges=[f'B{next_row}:B{next_row + len(matched_with_labels) - 1}'],
                        date_mmyyyy_ranges=[f'C{next_row}:C{next_row + len(matched_with_labels) - 1}'],
                        text_ranges=[f'E{next_row}:E{next_row + len(matched_with_labels) - 1}'],
                        number_ranges={
                            f'F{next_row}:F{next_row + len(matched_with_labels) - 1}': '#,##0.00',
                            f'G{next_row}:G{next_row + len(matched_with_labels) - 1}': '#,##0.00'
                        }
                    )
                    
                    logger.info(f"✅ Appended {len(matched_rows)} Phase 3 transactions to 'Matched' sheet")
                except Exception as e:
                    logger.error(f"❌ Error appending to 'Matched' sheet: {e}")
            else:
                logger.info("✅ No intercompany pairs found to append to 'Matched' sheet")
                
            # Update "Unmatched" sheet with remaining transactions (only if there were matches)
            if matched_rows:
                try:
                    # Sort unmatched by Column O for consistency
                    def sort_key(row):
                        if len(row) <= 14 or not row[14]:
                            return "zzz_empty"
                        col_o_val = safe_str(row[14])
                        try:
                            return f"{float(col_o_val):010.2f}"
                        except (ValueError, TypeError):
                            return col_o_val
                    
                    sorted_unmatched = sorted(unmatched_rows, key=sort_key)
                    header_ap = header_row[:16] if len(header_row) >= 16 else header_row
                    updated_data = [header_ap] + sorted_unmatched
                    
                    # Process rows to format Column B dates
                    updated_data = convert_column_b_to_serial(updated_data)
                    
                    unmatched_sheet.clear()
                    unmatched_sheet.update(updated_data, value_input_option='RAW')
                    
                    # Batch format all columns in a single API call
                    batch_format_columns(
                        unmatched_sheet,
                        date_ranges=['B2:B'],
                        date_mmyyyy_ranges=['C2:C'],
                        text_ranges=['E2:E'],
                        number_ranges={'F2:F': '#,##0.00', 'G2:G': '#,##0.00'}
                    )
                    
                    logger.info(f"✅ Updated 'Unmatched' sheet with {len(unmatched_rows)} remaining transactions")
                except Exception as e:
                    logger.error(f"❌ Error updating 'Unmatched' sheet: {e}")
            else:
                logger.info("✅ No matches found - 'Unmatched' sheet unchanged")
                
        except Exception as e:
            logger.error(f"Error in Phase 3 intercompany matching: {e}")
            
        # Summary
        logger.info(f"📊 Phase 3 complete:")
        logger.info(f"  • Found {len(matched_pairs)} intercompany pairs ({len(matched_rows)} transactions)")
        logger.info(f"  • Remaining unmatched: {len(unmatched_rows)} transactions")

    def _run_phase4(self) -> None:
        """Phase 4: Manual reconciliation with suggestive matching for material amounts"""
        logger.info("🔄 Phase 4: Starting manual reconciliation mode...")
        
        try:
            # Get unmatched sheet data (use UNFORMATTED_VALUE to preserve number types)
            unmatched_sheet = self.workbook.worksheet(UNMATCHED_SHEET_NAME)
            data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
            
            if len(data) <= 1:
                logger.info("  No unmatched transactions to process in Phase 4")
                return
            
            logger.info(f"Processing {len(data)-1} transactions for manual reconciliation")
            
            # Store original J/K values from both sheets for change detection
            logger.info("  📋 Storing original Column J/K values for change detection...")
            self._store_original_jk_values()
            
            # STEP 1: Initial sorting by Column A (GL) then Column B (Date)
            logger.info("  🔄 Step 1: Sorting by GL (Column A) then Date (Column B)...")
            sorted_data = self._initial_sort_unmatched(data)
            
            # STEP 2: Find suggested matches (Layer 1 & Layer 2) - returns match data without applying colors
            logger.info("  🔍 Step 2: Finding suggested matches...")
            match_data = self._find_suggestive_matches(sorted_data)
            
            # STEP 3: Priority re-sorting (imperfect pairs → perfect pairs → non-suggested)
            logger.info("  🔄 Step 3: Re-sorting by priority (imperfect → perfect → non-suggested)...")
            final_sorted_data = self._sort_by_priority_with_suggestions(sorted_data, match_data)
            
            # STEP 4: Write sorted data to sheet
            logger.info("  📝 Step 4: Writing sorted data to sheet...")
            self._write_sorted_data_to_unmatched(unmatched_sheet, final_sorted_data)
            
            # STEP 5: Apply color highlights to final sorted positions
            logger.info("  🎨 Step 5: Applying color highlights to suggested matches...")
            self._apply_colors_to_matches(unmatched_sheet, sorted_data, final_sorted_data, match_data)
            
            # STEP 6: Setup hotkeys and enter interactive mode
            self._start_interactive_mode(unmatched_sheet)
            
            logger.info("📊 Phase 4 complete")
            
        except Exception as e:
            logger.error(f"Error in Phase 4 manual reconciliation: {e}")
            import traceback
            traceback.print_exc()
    
    def _initial_sort_unmatched(self, data: List[List[str]]) -> List[List[str]]:
        """
        Step 1: Initial sorting by Column A (GL) then Column B (Date)
        Groups transactions by General Ledger, then sorts chronologically within each GL
        Returns: Sorted data with header
        """
        header_row = data[0]
        data_rows = data[1:]
        
        # Sort by Column A (GL) first, then Column B (Date) within each GL group
        def sort_key(row):
            # Column A (index 0) - General Ledger
            col_a = safe_str(row[0]) if len(row) > 0 else ""
            
            # Column B (index 1) - Date
            date_val = row[1] if len(row) > 1 else ""
            # Handle both numeric (date serial) and string dates
            if isinstance(date_val, (int, float)):
                date_sort_val = date_val  # Numeric date serial - sort directly
            else:
                date_sort_val = safe_str(date_val)  # String date - sort as string
            
            return (col_a, date_sort_val)
        
        sorted_rows = sorted(data_rows, key=sort_key)
        logger.info(f"     ✅ Sorted {len(sorted_rows)} transactions by GL (Column A) then Date (Column B)")
        
        return [header_row] + sorted_rows
    
    def _store_original_jk_values(self) -> None:
        """
        Store original Column J, K, and P values from both Matched and Unmatched sheets
        for later change detection when F10 is pressed
        
        Column P (index 15) is the unique identifier
        Column J (index 9) and Column K (index 10) are editable fields
        """
        try:
            # Clear any previously stored values
            self.phase4_original_matched_jk.clear()
            self.phase4_original_unmatched_jk.clear()
            
            # Store from Matched sheet
            try:
                matched_sheet = self.workbook.worksheet(MATCHED_SHEET_NAME)
                matched_data = matched_sheet.get(value_render_option='UNFORMATTED_VALUE')
                
                if len(matched_data) > 1:  # Has data beyond header
                    for row_idx, row in enumerate(matched_data[1:], start=2):  # Skip header, start at row 2
                        if len(row) > 15:  # Ensure P column exists (index 15)
                            unique_id = safe_str(row[15])  # Column P
                            if unique_id:  # Only store if unique ID exists
                                self.phase4_original_matched_jk[unique_id] = {
                                    'J': safe_str(row[9]) if len(row) > 9 else '',   # Column J
                                    'K': safe_str(row[10]) if len(row) > 10 else '',  # Column K
                                    'row': row_idx  # Store row number for updates
                                }
                    logger.info(f"     ✅ Stored {len(self.phase4_original_matched_jk)} original J/K values from Matched sheet")
            except Exception as e:
                logger.warning(f"     ⚠️ Could not read Matched sheet: {e}")
            
            # Store from Unmatched sheet
            try:
                unmatched_sheet = self.workbook.worksheet(UNMATCHED_SHEET_NAME)
                unmatched_data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
                
                if len(unmatched_data) > 1:  # Has data beyond header
                    for row_idx, row in enumerate(unmatched_data[1:], start=2):  # Skip header, start at row 2
                        if len(row) > 15:  # Ensure P column exists (index 15)
                            unique_id = safe_str(row[15])  # Column P
                            if unique_id:  # Only store if unique ID exists
                                self.phase4_original_unmatched_jk[unique_id] = {
                                    'J': safe_str(row[9]) if len(row) > 9 else '',   # Column J
                                    'K': safe_str(row[10]) if len(row) > 10 else '',  # Column K
                                    'row': row_idx  # Store row number for updates
                                }
                    logger.info(f"     ✅ Stored {len(self.phase4_original_unmatched_jk)} original J/K values from Unmatched sheet")
            except Exception as e:
                logger.warning(f"     ⚠️ Could not read Unmatched sheet: {e}")
                
        except Exception as e:
            logger.error(f"     ❌ Error storing original J/K values: {e}")
            import traceback
            traceback.print_exc()
    
    def _detect_jk_changes(self) -> dict:
        """
        Detect changes to Column J and/or K in both Matched and Unmatched sheets
        by comparing current values against stored originals
        
        Returns: {unique_id: {'J': new_val, 'K': new_val, 'source': 'Matched'/'Unmatched', 'row': row_number}}
        """
        changes = {}
        
        try:
            # Check Matched sheet for changes
            try:
                matched_sheet = self.workbook.worksheet(MATCHED_SHEET_NAME)
                matched_data = matched_sheet.get(value_render_option='UNFORMATTED_VALUE')
                
                if len(matched_data) > 1:  # Has data beyond header
                    for row_idx, row in enumerate(matched_data[1:], start=2):
                        if len(row) > 15:  # Ensure P column exists
                            unique_id = safe_str(row[15])  # Column P
                            if unique_id and unique_id in self.phase4_original_matched_jk:
                                original = self.phase4_original_matched_jk[unique_id]
                                current_j = safe_str(row[9]) if len(row) > 9 else ''
                                current_k = safe_str(row[10]) if len(row) > 10 else ''
                                
                                # Check if either J or K changed
                                if current_j != original['J'] or current_k != original['K']:
                                    changes[unique_id] = {
                                        'J': current_j,
                                        'K': current_k,
                                        'source': 'Matched',
                                        'row': row_idx
                                    }
                                    logger.info(f"     🔄 Change detected in Matched sheet, ID {unique_id}: J='{original['J']}'→'{current_j}', K='{original['K']}'→'{current_k}'")
            except Exception as e:
                logger.warning(f"     ⚠️ Could not check Matched sheet for changes: {e}")
            
            # Check Unmatched sheet for changes
            try:
                unmatched_sheet = self.workbook.worksheet(UNMATCHED_SHEET_NAME)
                unmatched_data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
                
                if len(unmatched_data) > 1:  # Has data beyond header
                    for row_idx, row in enumerate(unmatched_data[1:], start=2):
                        if len(row) > 15:  # Ensure P column exists
                            unique_id = safe_str(row[15])  # Column P
                            if unique_id and unique_id in self.phase4_original_unmatched_jk:
                                original = self.phase4_original_unmatched_jk[unique_id]
                                current_j = safe_str(row[9]) if len(row) > 9 else ''
                                current_k = safe_str(row[10]) if len(row) > 10 else ''
                                
                                # Check if either J or K changed
                                if current_j != original['J'] or current_k != original['K']:
                                    changes[unique_id] = {
                                        'J': current_j,
                                        'K': current_k,
                                        'source': 'Unmatched',
                                        'row': row_idx
                                    }
                                    logger.info(f"     🔄 Change detected in Unmatched sheet, ID {unique_id}: J='{original['J']}'→'{current_j}', K='{original['K']}'→'{current_k}'")
            except Exception as e:
                logger.warning(f"     ⚠️ Could not check Unmatched sheet for changes: {e}")
                
        except Exception as e:
            logger.error(f"     ❌ Error detecting J/K changes: {e}")
            import traceback
            traceback.print_exc()
        
        return changes
    
    def _sync_jk_changes_to_main(self, changes: dict) -> dict:
        """
        Update Column J and/or K in main sheet ("Due To/From GL - 08.31.25") based on detected changes,
        then read back calculated L/M/N/O values and update them in source sheets
        
        Args:
            changes: {unique_id: {'J': val, 'K': val, 'source': 'Matched'/'Unmatched', 'row': row_num}}
        
        Returns:
            {unique_id: {'L': val, 'M': val, 'N': val, 'O': val}} - Calculated values from main sheet
        """
        if not changes:
            return {}
        
        try:
            logger.info(f"\n📊 Syncing {len(changes)} J/K changes to main sheet...")
            
            main_sheet = self.workbook.worksheet(SOURCE_SHEET_NAME)
            main_data = main_sheet.get(value_render_option='UNFORMATTED_VALUE')
            
            # Build a map: unique_id → main_sheet_row_number
            id_to_row = {}
            for row_idx, row in enumerate(main_data[1:], start=2):  # Skip header
                if len(row) > 15:  # Ensure P column exists
                    unique_id = safe_str(row[15])
                    if unique_id:
                        id_to_row[unique_id] = row_idx
            
            # Step 1: Update J/K in main sheet
            updates = []
            for unique_id, change_info in changes.items():
                if unique_id in id_to_row:
                    main_row = id_to_row[unique_id]
                    
                    # Update Column J (column index 10 in A1 notation = J)
                    updates.append({
                        'range': f'J{main_row}',
                        'values': [[change_info['J']]]
                    })
                    
                    # Update Column K (column index 11 in A1 notation = K)
                    updates.append({
                        'range': f'K{main_row}',
                        'values': [[change_info['K']]]
                    })
                    
                    logger.info(f"   • Updating main sheet row {main_row} (ID {unique_id}): J='{change_info['J']}', K='{change_info['K']}'")
                else:
                    logger.warning(f"   ⚠️ Unique ID {unique_id} not found in main sheet")
            
            # Batch update J/K values
            if updates:
                main_sheet.batch_update(updates)
                logger.info(f"   ✅ Updated {len(updates)} cells in main sheet")
                
                # Small delay to allow formulas to recalculate
                time.sleep(0.5)
            
            # Step 2: Read back L/M/N/O calculated values
            logger.info(f"\n📊 Reading calculated L/M/N/O values from main sheet...")
            main_data = main_sheet.get(value_render_option='UNFORMATTED_VALUE')  # Re-read after updates
            
            calculated_values = {}
            for unique_id, change_info in changes.items():
                if unique_id in id_to_row:
                    main_row_idx = id_to_row[unique_id] - 2  # Convert to 0-based index (minus header)
                    if main_row_idx >= 0 and main_row_idx < len(main_data) - 1:
                        row = main_data[main_row_idx + 1]  # +1 to skip header in data array
                        
                        calculated_values[unique_id] = {
                            'L': safe_str(row[11]) if len(row) > 11 else '',  # Column L
                            'M': safe_str(row[12]) if len(row) > 12 else '',  # Column M
                            'N': safe_str(row[13]) if len(row) > 13 else '',  # Column N
                            'O': safe_str(row[14]) if len(row) > 14 else '',  # Column O
                        }
                        logger.info(f"   • Read ID {unique_id}: L='{calculated_values[unique_id]['L']}', M='{calculated_values[unique_id]['M']}', N='{calculated_values[unique_id]['N']}', O='{calculated_values[unique_id]['O']}'")
            
            # Step 3: Update L/M/N/O in source sheets (Matched or Unmatched)
            logger.info(f"\n📊 Updating calculated L/M/N/O values in source sheets...")
            
            # Group changes by source sheet
            matched_updates = []
            unmatched_updates = []
            
            for unique_id, change_info in changes.items():
                if unique_id in calculated_values:
                    calc_vals = calculated_values[unique_id]
                    source_row = change_info['row']
                    
                    # Build batch update for all 4 columns L/M/N/O
                    updates_list = matched_updates if change_info['source'] == 'Matched' else unmatched_updates
                    
                    updates_list.append({'range': f'L{source_row}', 'values': [[calc_vals['L']]]})
                    updates_list.append({'range': f'M{source_row}', 'values': [[calc_vals['M']]]})
                    updates_list.append({'range': f'N{source_row}', 'values': [[calc_vals['N']]]})
                    updates_list.append({'range': f'O{source_row}', 'values': [[calc_vals['O']]]})
            
            # Apply updates to Matched sheet
            if matched_updates:
                matched_sheet = self.workbook.worksheet(MATCHED_SHEET_NAME)
                matched_sheet.batch_update(matched_updates)
                logger.info(f"   ✅ Updated {len(matched_updates)} cells in Matched sheet")
            
            # Apply updates to Unmatched sheet
            if unmatched_updates:
                unmatched_sheet = self.workbook.worksheet(UNMATCHED_SHEET_NAME)
                unmatched_sheet.batch_update(unmatched_updates)
                logger.info(f"   ✅ Updated {len(unmatched_updates)} cells in Unmatched sheet")
            
            logger.info(f"✅ J/K sync complete!\n")
            return calculated_values
            
        except Exception as e:
            logger.error(f"❌ Error syncing J/K changes: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _find_suggestive_matches(self, data: List[List[str]]) -> dict:
        """
        Step 2: Find suggested matches based on Layer 1 & Layer 2 rules
        Returns: Dictionary with match information (does NOT apply colors yet)
        
        Returns structure:
        {
            'layer1_matches': {amount: [(row_idx, column), ...]},
            'layer2_matches': [(property, amount, [(row_idx, column), ...])],
            'all_matched_rows': set of row indices that have suggested matches
        }
        """
        logger.info(f"     Layer 1: Amounts ≥ ${PHASE4_THRESHOLD:,} (across all properties)")
        logger.info(f"     Layer 2: Any amount within same Main Property GL")
        
        # Layer 1: Parse amounts >= threshold (across all properties)
        debit_amounts_layer1 = {}  # {amount: [(row_index, 'F')]}
        credit_amounts_layer1 = {}  # {amount: [(row_index, 'G')]}
        
        # Layer 2: Parse amounts by property (any amount)
        debit_by_property = {}
        credit_by_property = {}
        
        for i, row in enumerate(data[1:], 1):  # Skip header, 1-indexed
            if len(row) <= 6:
                continue
            
            # Get property from Column A (index 0)
            property_code = safe_str(row[0]) if len(row) > 0 else ""
            
            # Get raw values (could be float or string)
            debit_raw = row[5] if len(row) > 5 else ""
            credit_raw = row[6] if len(row) > 6 else ""
            
            # Column F (index 5) - Debit
            try:
                if isinstance(debit_raw, (int, float)):
                    debit_val = float(debit_raw)
                elif isinstance(debit_raw, str):
                    debit_str = debit_raw.strip().replace(',', '').replace('$', '').replace(' ', '')
                    debit_val = float(debit_str) if debit_str and debit_str not in ('', '-') else 0.0
                else:
                    debit_val = 0.0
                    
                if abs(debit_val) > 0.01:
                    amount = abs(debit_val)
                    
                    # Layer 1: Track if >= threshold
                    if amount >= PHASE4_THRESHOLD:
                        if amount not in debit_amounts_layer1:
                            debit_amounts_layer1[amount] = []
                        debit_amounts_layer1[amount].append((i, 'F'))
                    
                    # Layer 2: Track by property (all amounts)
                    if property_code:
                        if property_code not in debit_by_property:
                            debit_by_property[property_code] = {}
                        if amount not in debit_by_property[property_code]:
                            debit_by_property[property_code][amount] = []
                        debit_by_property[property_code][amount].append((i, 'F'))
                            
            except (ValueError, IndexError):
                pass
            
            # Column G (index 6) - Credit
            try:
                if isinstance(credit_raw, (int, float)):
                    credit_val = float(credit_raw)
                elif isinstance(credit_raw, str):
                    credit_str = credit_raw.strip().replace(',', '').replace('$', '').replace(' ', '')
                    credit_val = float(credit_str) if credit_str and credit_str not in ('', '-') else 0.0
                else:
                    credit_val = 0.0
                    
                if abs(credit_val) > 0.01:
                    amount = abs(credit_val)
                    
                    # Layer 1: Track if >= threshold
                    if amount >= PHASE4_THRESHOLD:
                        if amount not in credit_amounts_layer1:
                            credit_amounts_layer1[amount] = []
                        credit_amounts_layer1[amount].append((i, 'G'))
                    
                    # Layer 2: Track by property (all amounts)
                    if property_code:
                        if property_code not in credit_by_property:
                            credit_by_property[property_code] = {}
                        if amount not in credit_by_property[property_code]:
                            credit_by_property[property_code][amount] = []
                        credit_by_property[property_code][amount].append((i, 'G'))
                            
            except (ValueError, IndexError):
                pass
        
        # Find matching amounts for Layer 1
        matching_amounts_layer1 = set(debit_amounts_layer1.keys()) & set(credit_amounts_layer1.keys())
        
        # Find matching amounts for Layer 2
        matching_amounts_layer2 = []
        for property_code in set(debit_by_property.keys()) & set(credit_by_property.keys()):
            debit_amounts = set(debit_by_property[property_code].keys())
            credit_amounts = set(credit_by_property[property_code].keys())
            common_amounts = debit_amounts & credit_amounts
            
            for amount in common_amounts:
                # Exclude if already covered by Layer 1
                if amount >= PHASE4_THRESHOLD and amount in matching_amounts_layer1:
                    continue
                
                debit_rows = debit_by_property[property_code][amount]
                credit_rows = credit_by_property[property_code][amount]
                matching_amounts_layer2.append((property_code, amount, debit_rows + credit_rows))
        
        logger.info(f"     📊 Found {len(matching_amounts_layer1)} Layer 1 matches (≥ ${PHASE4_THRESHOLD:,})")
        logger.info(f"     📊 Found {len(matching_amounts_layer2)} Layer 2 matches (same property, < ${PHASE4_THRESHOLD:,})")
        
        # Build match data structure
        layer1_matches = {}
        for amount in matching_amounts_layer1:
            all_row_cols = debit_amounts_layer1[amount] + credit_amounts_layer1[amount]
            layer1_matches[amount] = all_row_cols
            logger.info(f"     💡 Layer 1: {len(all_row_cols)} transactions @ ${amount:,.2f}")
        
        layer2_matches = []
        for property_code, amount, row_cols in matching_amounts_layer2:
            layer2_matches.append((property_code, amount, row_cols))
            logger.info(f"     💡 Layer 2: {len(row_cols)} transactions @ ${amount:,.2f} (property: {property_code})")
        
        # Collect all matched row indices
        all_matched_rows = set()
        for row_cols in layer1_matches.values():
            for row_idx, _ in row_cols:
                all_matched_rows.add(row_idx)
        for _, _, row_cols in layer2_matches:
            for row_idx, _ in row_cols:
                all_matched_rows.add(row_idx)
        
        return {
            'layer1_matches': layer1_matches,
            'layer2_matches': layer2_matches,
            'all_matched_rows': all_matched_rows
        }
    
    def _sort_by_priority_with_suggestions(self, data: List[List[str]], match_data: dict) -> List[List[str]]:
        """
        Step 3: Priority re-sorting
        Priority 1 (TOP): Imperfect pairs (3+ transactions with same amount) - grouped by match
        Priority 2 (MIDDLE): Perfect pairs (exactly 2 transactions with same amount) - grouped by match
        Priority 3 (BOTTOM): Non-suggested (no match) - sorted by GL then date
        
        Match groups stay together (same color = same match group)
        
        Returns: Re-sorted data with header
        """
        header_row = data[0]
        data_rows = data[1:]
        
        layer1_matches = match_data['layer1_matches']
        layer2_matches = match_data['layer2_matches']
        all_matched_rows = match_data['all_matched_rows']
        
        # Categorize transactions - keep match groups together
        imperfect_match_groups = []  # Priority 1: List of match groups (each group is a list of rows)
        perfect_match_groups = []    # Priority 2: List of match groups (each group is a list of rows)
        non_suggested = []            # Priority 3: no match
        
        # Track which rows have been categorized
        categorized_rows = set()
        
        # Process Layer 1 matches - keep each match group together
        for amount, row_cols in layer1_matches.items():
            count = len(row_cols)
            rows_for_this_match = []
            
            for row_idx, column in row_cols:
                if row_idx <= len(data_rows):
                    rows_for_this_match.append(data_rows[row_idx - 1])
                    categorized_rows.add(row_idx - 1)
            
            # Keep this match group together
            if count == 2:
                perfect_match_groups.append(rows_for_this_match)
            else:
                imperfect_match_groups.append(rows_for_this_match)
        
        # Process Layer 2 matches - keep each match group together
        for property_code, amount, row_cols in layer2_matches:
            count = len(row_cols)
            rows_for_this_match = []
            
            for row_idx, column in row_cols:
                if row_idx <= len(data_rows) and (row_idx - 1) not in categorized_rows:
                    rows_for_this_match.append(data_rows[row_idx - 1])
                    categorized_rows.add(row_idx - 1)
            
            # Keep this match group together
            if rows_for_this_match:
                if count == 2:
                    perfect_match_groups.append(rows_for_this_match)
                else:
                    imperfect_match_groups.append(rows_for_this_match)
        
        # Collect non-suggested transactions
        for idx, row in enumerate(data_rows):
            if idx not in categorized_rows:
                non_suggested.append(row)
        
        # Flatten match groups into single lists (groups stay together)
        imperfect_pairs = []
        for match_group in imperfect_match_groups:
            imperfect_pairs.extend(match_group)
        
        perfect_pairs = []
        for match_group in perfect_match_groups:
            perfect_pairs.extend(match_group)
        
        # Sort only non-suggested by Column A (GL) then Column B (Date)
        def date_sort_key(row):
            # Column A (index 0) - General Ledger
            col_a = safe_str(row[0]) if len(row) > 0 else ""
            
            # Column B (index 1) - Date
            date_val = row[1] if len(row) > 1 else ""
            if isinstance(date_val, (int, float)):
                date_sort_val = date_val  # Numeric date serial
            else:
                date_sort_val = safe_str(date_val)  # String date
            
            return (col_a, date_sort_val)
        
        non_suggested_sorted = sorted(non_suggested, key=date_sort_key)
        
        logger.info(f"     📊 Priority 1 (Imperfect pairs): {len(imperfect_pairs)} transactions in {len(imperfect_match_groups)} match groups")
        logger.info(f"     📊 Priority 2 (Perfect pairs): {len(perfect_pairs)} transactions in {len(perfect_match_groups)} match groups")
        logger.info(f"     📊 Priority 3 (Non-suggested): {len(non_suggested_sorted)} transactions (sorted by GL then date)")
        
        # Combine in priority order: imperfect groups → perfect groups → non-suggested
        final_sorted_rows = imperfect_pairs + perfect_pairs + non_suggested_sorted
        
        return [header_row] + final_sorted_rows
    
    def _write_sorted_data_to_unmatched(self, unmatched_sheet, data: List[List[str]]) -> None:
        """
        Step 4: Write sorted data to Unmatched sheet
        """
        # Process dates in Column B and C
        processed_data = convert_column_b_to_serial(data)
        
        # Clear and write
        unmatched_sheet.clear()
        unmatched_sheet.update(processed_data, value_input_option='RAW')
        
        # Batch format all columns in a single API call
        batch_format_columns(
            unmatched_sheet,
            date_ranges=['B2:B'],
            date_mmyyyy_ranges=['C2:C'],
            text_ranges=['E2:E'],
            number_ranges={'F2:F': '#,##0.00', 'G2:G': '#,##0.00'}
        )
        
        logger.info(f"     ✅ Wrote {len(data)-1} sorted transactions to 'Unmatched' sheet")
    
    def _apply_colors_to_matches(self, unmatched_sheet, initial_sorted_data: List[List[str]], final_sorted_data: List[List[str]], match_data: dict) -> None:
        """
        Step 5: Apply color highlights to suggested matches in their FINAL sorted positions
        
        The match_data contains row indices from the INITIAL sorted data (after Step 1).
        We need to find where these rows ended up in the FINAL sorted data (after Step 3).
        
        Args:
            initial_sorted_data: Data after Step 1 (sorted by A→J→K)
            final_sorted_data: Data after Step 3 (priority sorted)
            match_data: Match information with row indices referring to initial_sorted_data
        """
        layer1_matches = match_data['layer1_matches']
        layer2_matches = match_data['layer2_matches']
        
        batch_requests = []
        color_index = 0
        
        # Process Layer 1 matches - group by amount and color
        for amount, row_cols in sorted(layer1_matches.items()):
            if color_index >= len(self.phase4_colors):
                logger.warning(f"     ⚠️  Reached maximum color limit ({len(self.phase4_colors)}), skipping remaining matches")
                break
            
            color = self.phase4_colors[color_index]
            self.phase4_used_colors.add(color_index)
            color_index += 1
            
            # For each transaction in this match group, find it in final_sorted_data and color it
            for row_idx, column in row_cols:
                # row_idx is 1-indexed referring to initial sorted data
                # Get the actual row data from initial_sorted_data
                if row_idx < len(initial_sorted_data):
                    initial_row = initial_sorted_data[row_idx]
                    
                    # Get the amount value from the specific column we're matching
                    initial_amount = safe_str(initial_row[5] if column == 'F' else initial_row[6])
                    
                    # Search for this row in final_sorted_data by content matching
                    for final_idx, final_row in enumerate(final_sorted_data[1:], 1):  # Skip header, 1-indexed
                        # Match by comparing key columns to identify the same transaction
                        # Compare the amount in the same column to distinguish between rows with same metadata
                        final_amount = safe_str(final_row[5] if column == 'F' else final_row[6])
                        
                        if (len(final_row) > 10 and len(initial_row) > 10 and
                            safe_str(final_row[0]) == safe_str(initial_row[0]) and  # Column A (GL)
                            safe_str(final_row[9]) == safe_str(initial_row[9]) and  # Column J
                            safe_str(final_row[10]) == safe_str(initial_row[10]) and  # Column K
                            safe_str(final_row[1]) == safe_str(initial_row[1]) and  # Column B (date)
                            initial_amount == final_amount):  # Match amount in the same column (F or G)
                            
                            # Found the row! Apply color to the specific column (F or G) where the match was found
                            start_col = 5 if column == 'F' else 6
                            end_col = start_col + 1
                            
                            batch_requests.append({
                                "repeatCell": {
                                    "range": {
                                        "sheetId": unmatched_sheet.id,
                                        "startRowIndex": final_idx,
                                        "endRowIndex": final_idx + 1,
                                        "startColumnIndex": start_col,
                                        "endColumnIndex": end_col
                                    },
                                    "cell": {
                                        "userEnteredFormat": {
                                            "backgroundColor": color
                                        }
                                    },
                                    "fields": "userEnteredFormat.backgroundColor"
                                }
                            })
                            break  # Found and colored this row, move to next
        
        # Process Layer 2 matches
        for property_code, amount, row_cols in layer2_matches:
            if color_index >= len(self.phase4_colors):
                logger.warning(f"     ⚠️  Reached maximum color limit ({len(self.phase4_colors)}), skipping remaining matches")
                break
            
            color = self.phase4_colors[color_index]
            self.phase4_used_colors.add(color_index)
            color_index += 1
            
            for row_idx, column in row_cols:
                # Get the actual row data from initial_sorted_data
                if row_idx < len(initial_sorted_data):
                    initial_row = initial_sorted_data[row_idx]
                    
                    # Get the amount value from the specific column we're matching
                    initial_amount = safe_str(initial_row[5] if column == 'F' else initial_row[6])
                    
                    # Search for this row in final_sorted_data
                    for final_idx, final_row in enumerate(final_sorted_data[1:], 1):  # Skip header, 1-indexed
                        # Match by comparing key columns to identify the same transaction
                        # Compare the amount in the same column to distinguish between rows with same metadata
                        final_amount = safe_str(final_row[5] if column == 'F' else final_row[6])
                        
                        if (len(final_row) > 10 and len(initial_row) > 10 and
                            safe_str(final_row[0]) == safe_str(initial_row[0]) and  # Column A (GL)
                            safe_str(final_row[9]) == safe_str(initial_row[9]) and  # Column J
                            safe_str(final_row[10]) == safe_str(initial_row[10]) and  # Column K
                            safe_str(final_row[1]) == safe_str(initial_row[1]) and  # Column B (date)
                            initial_amount == final_amount):  # Match amount in the same column (F or G)
                            
                            # Found the row! Apply color to the specific column (F or G)
                            start_col = 5 if column == 'F' else 6
                            end_col = start_col + 1
                            
                            batch_requests.append({
                                "repeatCell": {
                                    "range": {
                                        "sheetId": unmatched_sheet.id,
                                        "startRowIndex": final_idx,
                                        "endRowIndex": final_idx + 1,
                                        "startColumnIndex": start_col,
                                        "endColumnIndex": end_col
                                    },
                                    "cell": {
                                        "userEnteredFormat": {
                                            "backgroundColor": color
                                        }
                                    },
                                    "fields": "userEnteredFormat.backgroundColor"
                                }
                            })
                            break  # Found and colored this row, move to next
        
        # Apply all color changes in one batch
        if batch_requests:
            self.workbook.batch_update({"requests": batch_requests})
            logger.info(f"     ✅ Applied {len(batch_requests)} color highlights")
        
        # Update color index for manual coloring
        self.phase4_color_index = color_index
    
    def _sort_unmatched_sheet_by_phase4_suggestions(self) -> None:
        """
        Sort the Unmatched sheet after Phase 4 suggestions are applied.
        Priority order:
        A. Suggested matches (with color highlights) - sorted by Column A → J → K
        B. Non-suggested transactions (no color) - sorted by Column A → J → K
        """
        logger.info("  🔄 Sorting 'Unmatched' sheet by Phase 4 suggestions...")
        
        try:
            unmatched_sheet = self.workbook.worksheet("Unmatched")
            
            # Get data with values
            data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
            if len(data) <= 1:
                logger.info("     No data in 'Unmatched' sheet to sort")
                return
            
            header_row = data[0]
            data_rows = data[1:]
            
            # Sort all rows by: Column A (index 0), Column J (index 9), Column K (index 10)
            def sort_key(row):
                col_a = safe_str(row[0]) if len(row) > 0 else ""
                col_j = safe_str(row[9]) if len(row) > 9 else ""
                col_k = safe_str(row[10]) if len(row) > 10 else ""
                return (col_a, col_j, col_k)
            
            sorted_rows = sorted(data_rows, key=sort_key)
            
            # Rebuild data with header
            sorted_data = [header_row] + sorted_rows
            
            # Process dates in Column B and C
            sorted_data = convert_column_b_to_serial(sorted_data)
            
            # Write sorted data back
            unmatched_sheet.clear()
            unmatched_sheet.update(sorted_data, value_input_option='RAW')
            
            # Batch format all columns in a single API call
            batch_format_columns(
                unmatched_sheet,
                date_ranges=['B2:B'],
                date_mmyyyy_ranges=['C2:C'],
                text_ranges=['E2:E'],
                number_ranges={'F2:F': '#,##0.00', 'G2:G': '#,##0.00'}
            )
            
            logger.info(f"     ✅ Sorted {len(data_rows)} transactions in 'Unmatched' sheet")
            
        except Exception as e:
            logger.error(f"     ❌ Error sorting 'Unmatched' sheet: {e}")
    
    def _start_interactive_mode(self, unmatched_sheet) -> None:
        """Start interactive mode with hotkey listener for F10 only"""
        # Clear any existing keyboard hooks first to prevent duplicates
        keyboard.unhook_all()
        
        logger.info("\n" + "="*60)
        logger.info("🎨 PHASE 4: MANUAL RECONCILIATION MODE")
        logger.info("="*60)
        logger.info(f"📌 Suggested matches have been highlighted in the 'Unmatched' sheet")
        logger.info(f"📌 Use Google Sheets to apply colors to matching transactions:")
        logger.info(f"   1. Select cell(s) in Column F or G")
        logger.info(f"   2. Click 'Phase 4' > 'Apply Color to Selection'")
        logger.info(f"   3. Repeat for matching pairs (same color = matched)")
        logger.info("")
        logger.info("⌨️  HOTKEYS:")
        logger.info(f"   • F9         = Apply color to selected cell (triggers Ctrl+Alt+Shift+1 in Google Sheets)")
        logger.info(f"   • F10        = Validate and process all color-matched pairs")
        logger.info(f"   • Ctrl+Enter = Proceed to Phase 5 (Subsidiary Ledger T-Accounts)")
        logger.info(f"   • Ctrl+C     = Exit without processing")
        logger.info("")
        logger.info("💡 TIP: Select cells in Google Sheets, press F9 to color, same color = matched pair")
        logger.info("="*60)
        
        self.phase4_running = True
        
        # Setup hotkey handlers
        # F9: Simulate Ctrl+Shift+1 to trigger Google Sheets macro
        keyboard.on_press_key('f9', lambda _: self._handle_f9_macro())
        logger.info("✅ F9 hotkey registered")
        
        # F10: Process all matches
        keyboard.on_press_key(PHASE4_HOTKEY_PROCESS, lambda _: self._handle_process_hotkey(unmatched_sheet))
        logger.info(f"✅ F10 hotkey registered (key: '{PHASE4_HOTKEY_PROCESS}')")
        
        # Ctrl+Enter: Proceed to Phase 5
        keyboard.add_hotkey('ctrl+enter', lambda: self._handle_enter_phase5())
        logger.info("✅ Ctrl+Enter hotkey registered (proceed to Phase 5)")
        
        # Setup Ctrl+C handler
        def signal_handler(sig, frame):
            logger.info("\n\n🛑 Exiting Phase 4 manual reconciliation mode...")
            self.phase4_running = False
            keyboard.unhook_all()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Keep script running until Ctrl+C
        try:
            while self.phase4_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("\n\n🛑 Exiting Phase 4...")
            keyboard.unhook_all()
    
    def _handle_f9_macro(self) -> None:
        """Handle F9 hotkey - Simulate Ctrl+Alt+Shift+1 to trigger Google Sheets macro"""
        logger.info("🎨 F9 pressed - Triggering Google Sheets color macro (Ctrl+Alt+Shift+1)...")
        
        # Simulate Ctrl+Alt+Shift+1 keypress to trigger Google Sheets macro
        keyboard.press_and_release('ctrl+alt+shift+1')
        
        # Brief pause to let the macro execute
        time.sleep(0.2)
    # Apps Script applies colors instantly without Python communication
    
    def _handle_enter_phase5(self) -> None:
        """Handle Ctrl+Enter key - Exit Phase 4 and proceed to Phase 5"""
        logger.info("\n" + "="*60)
        logger.info("⏭️  CTRL+ENTER PRESSED - PROCEEDING TO PHASE 5")
        logger.info("="*60)
        
        # Exit Phase 4 interactive mode
        self.phase4_running = False
        keyboard.unhook_all()
        
        # Run Phase 5
        self._run_phase5()
        
        logger.info("\n✅ Phase 5 complete - Exiting...")
        sys.exit(0)
    
    def _handle_process_hotkey(self, unmatched_sheet) -> None:
        """Handle F10 hotkey - Process all color-matched pairs"""
        try:
            logger.info("\n" + "="*60)
            logger.info("⚙️  F10 PRESSED - PROCESSING COLOR-MATCHED PAIRS")
            logger.info("="*60)
            
            # NEW: Step 0 - Check for Column J/K changes and sync with main sheet
            logger.info("📊 Step 0: Checking for Column J/K changes...")
            changes = self._detect_jk_changes()
            
            if changes:
                logger.info(f"   🔄 Found {len(changes)} rows with J/K changes")
                # Sync changes to main sheet and read back calculated L/M/N/O values
                self._sync_jk_changes_to_main(changes)
            else:
                logger.info("   ✅ No J/K changes detected")
            
            logger.info("📊 Step 1: Reading colors from 'Unmatched' sheet...")
            
            # Get all data and formatting from unmatched sheet (use UNFORMATTED_VALUE)
            data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
            logger.info(f"   • Loaded {len(data)-1} transaction rows (excluding header)")
            
            # Extract colors from cells in columns F and G
            logger.info("📊 Step 2: Extracting cell colors...")
            color_map = self._extract_colors_from_sheet(unmatched_sheet, data)
            
            # Group CELLS by color (not rows)
            # color_map = {(row_idx, col_name, amount): color_key}
            color_groups = {}  # {color_key: [(row_idx, col_name, amount), ...]}
            
            for cell_key, color_key in color_map.items():
                if color_key not in color_groups:
                    color_groups[color_key] = []
                color_groups[color_key].append(cell_key)
            
            logger.info(f"   • Found {len(color_groups)} unique color groups")
            logger.info(f"   • Total colored cells: {len(color_map)}")
            
            # Validate and process each color group
            logger.info("📊 Step 3: Validating color groups (checking debit = credit)...")
            matched_pairs = []
            unbalanced_groups = []
            
            for color_key, cell_list in color_groups.items():
                # Calculate net sum for this color group by summing amounts directly
                debit_sum = 0
                credit_sum = 0
                row_indices = set()
                
                for row_idx, col_name, amount in cell_list:
                    row_indices.add(row_idx)
                    
                    if col_name == 'F':  # Debit column
                        debit_sum += amount
                    elif col_name == 'G':  # Credit column
                        credit_sum += amount
                
                # Skip single-cell groups
                if len(cell_list) < 2:
                    continue
                
                # Check if net is zero (within small tolerance for floating point)
                net = debit_sum - credit_sum
                if abs(net) < 0.01:
                    # Valid match!
                    matched_pairs.append(sorted(list(row_indices)))
                    logger.info(f"   ✅ VALID: {len(row_indices)} rows, {len(cell_list)} cells, Debit: ${debit_sum:,.2f}, Credit: ${credit_sum:,.2f}")
                else:
                    # Unbalanced
                    unbalanced_groups.append((len(row_indices), net))
                    if len(row_indices) <= 10:  # Only log small unbalanced groups
                        logger.warning(f"   ⚠️  Unbalanced: {len(row_indices)} rows, {len(cell_list)} cells, Debit: ${debit_sum:,.2f}, Credit: ${credit_sum:,.2f}, Net: ${net:,.2f}")
            
            # Summary
            logger.info("\n" + "="*60)
            logger.info("📊 VALIDATION SUMMARY:")
            logger.info(f"   ✅ Valid matched pairs: {len(matched_pairs)}")
            logger.info(f"   ⚠️  Unbalanced groups: {len(unbalanced_groups)}")
            if unbalanced_groups:
                large_unbalanced = [g for g in unbalanced_groups if g[0] > 10]
                if large_unbalanced:
                    logger.info(f"      (Including {len(large_unbalanced)} large unbalanced groups)")
            logger.info("="*60)
            
            # Process matched pairs
            if matched_pairs:
                logger.info(f"\n📝 Step 4: Processing {len(matched_pairs)} matched pairs...")
                total_transactions = sum(len(p) for p in matched_pairs)
                logger.info(f"   • Total transactions to move: {total_transactions}")
                
                self._process_phase4_matches(unmatched_sheet, data, matched_pairs)
                
                logger.info("\n" + "="*60)
                logger.info("✅ SUCCESS!")
                logger.info(f"   • Moved {total_transactions} transactions to 'Matched' sheet")
                logger.info(f"   • {len(matched_pairs)} matched pairs processed")
                logger.info("="*60)
            else:
                logger.info("\n" + "="*60)
                logger.info("⚠️  NO VALID MATCHES FOUND")
                logger.info("   Make sure matching transactions have:")
                logger.info("   • Same background color")
                logger.info("   • Net sum = 0 (Debit - Credit)")
                logger.info("="*60)
            
        except Exception as e:
            logger.error("\n" + "="*60)
            logger.error(f"❌ ERROR IN PROCESSING: {e}")
            logger.error("="*60)
            import traceback
            traceback.print_exc()
            import sys
            sys.stdout.flush()
            sys.stderr.flush()
    
    def _extract_colors_from_sheet(self, sheet, data: List[List[str]]) -> Dict[Tuple[int, str, float], str]:
        """
        Extract background colors from columns F and G
        Returns: {(row_idx, col_name, amount): color_key}
        
        This tracks EACH colored cell individually (not just per row) so that:
        - Row 5 Column F (green, $100) and Row 5 Column G (blue, $50) are separate entries
        - Multiple cells in same row can have different colors
        - Amounts are included for accurate grouping
        """
        color_map = {}
        
        # Use the spreadsheet.get() method to retrieve cell formatting
        try:
            # Get formatting for columns F and G
            sheet_data = self.workbook.fetch_sheet_metadata({
                'includeGridData': True,
                'ranges': [f"'{UNMATCHED_SHEET_NAME}'!F:G"]
            })
            
            # Extract colors from grid data
            for sheet_info in sheet_data.get('sheets', []):
                if sheet_info['properties']['title'] != UNMATCHED_SHEET_NAME:
                    continue
                
                grid_data = sheet_info.get('data', [])
                if not grid_data:
                    continue
                
                row_data_list = grid_data[0].get('rowData', [])
                
                for row_idx, row_data in enumerate(row_data_list):
                    if row_idx == 0:  # Skip header
                        continue
                    
                    values = row_data.get('values', [])
                    
                    # Check BOTH Column F and Column G (don't break early)
                    for col_idx, cell_data in enumerate(values):
                        if col_idx > 1:  # Only F and G (indices 0, 1)
                            break
                        
                        col_name = 'F' if col_idx == 0 else 'G'
                        
                        # Check for background color
                        user_format = cell_data.get('effectiveFormat', {})
                        bg_color = user_format.get('backgroundColor', {})
                        
                        # Only process if cell has a color (not white/default)
                        if bg_color and any(bg_color.get(k, 0) > 0 for k in ['red', 'green', 'blue']):
                            # Get the cell value (amount)
                            if row_idx < len(data):
                                row = data[row_idx]
                                amount_str = row[5] if col_idx == 0 else row[6] if len(row) > 6 else ""
                                
                                # Parse amount (handle both string and numeric types)
                                try:
                                    # Convert to string first if it's already a number
                                    if isinstance(amount_str, (int, float)):
                                        amount = abs(float(amount_str))
                                    else:
                                        amount_clean = str(amount_str).strip().replace(',', '').replace('$', '')
                                        amount = abs(float(amount_clean)) if amount_clean and amount_clean != '0' else 0.0
                                    
                                    if amount > 0:  # Only track non-zero colored cells
                                        # Create color key from RGB values
                                        color_key = f"{bg_color.get('red', 0):.3f}_{bg_color.get('green', 0):.3f}_{bg_color.get('blue', 0):.3f}"
                                        
                                        # Store with row, column, and amount as key
                                        color_map[(row_idx, col_name, amount)] = color_key
                                        
                                except (ValueError, IndexError):
                                    pass
            
        except Exception as e:
            logger.error(f"Error extracting colors: {e}")
            import traceback
            traceback.print_exc()
        
        return color_map
    
    def _show_unpaired_alert(self, data: List[List[str]], unpaired_indices: List[int]) -> None:
        """Show popup alert for unpaired highlighted transactions"""
        message = "The following highlighted transactions don't have matching pairs:\n\n"
        
        for idx in unpaired_indices[:10]:  # Limit to first 10
            if idx < len(data):
                row = data[idx]
                # Get relevant info from row
                ref = row[0] if len(row) > 0 else ""
                debit = row[5] if len(row) > 5 else ""
                credit = row[6] if len(row) > 6 else ""
                
                if debit and debit != "0":
                    message += f"Row {idx + 1}: ${debit} (DEBIT) - Ref: {ref}\n"
                elif credit and credit != "0":
                    message += f"Row {idx + 1}: ${credit} (CREDIT) - Ref: {ref}\n"
        
        if len(unpaired_indices) > 10:
            message += f"\n... and {len(unpaired_indices) - 10} more"
        
        message += "\n\nPlease ensure each highlighted transaction has a matching pair with the same color."
        
        messagebox.showwarning("Unpaired Transactions", message)
    
    def _process_phase4_matches(self, unmatched_sheet, data: List[List[str]], matched_pairs: List[List[int]]) -> None:
        """Move matched pairs to Matched sheet and remove from Unmatched"""
        try:
            logger.info("   • Collecting matched transactions...")
            # Collect all matched rows
            matched_rows = []
            matched_indices = set()
            
            for pair in matched_pairs:
                for row_idx in pair:
                    if row_idx < len(data) and row_idx > 0:  # Skip header
                        row = data[row_idx][:16] if len(data[row_idx]) >= 16 else data[row_idx]
                        matched_rows.append(row + ["Phase 4"])
                        matched_indices.add(row_idx)
            
            logger.info(f"   • Collected {len(matched_rows)} transactions from {len(matched_pairs)} pairs")
            
            # Append to Matched sheet
            if matched_rows:
                logger.info("   • Appending to 'Matched' sheet...")
                matched_sheet = self.workbook.worksheet(MATCHED_SHEET_NAME)
                existing_data = matched_sheet.get(value_render_option='UNFORMATTED_VALUE')
                next_row = len(existing_data) + 1
                
                # Process rows to format Column B dates
                matched_rows = convert_column_b_to_serial([["Header"]] + matched_rows)[1:]  # Skip fake header
                
                start_range = f"A{next_row}"
                end_col = chr(65 + len(matched_rows[0]) - 1)
                end_range = f"{end_col}{next_row + len(matched_rows) - 1}"
                
                matched_sheet.update(
                    values=matched_rows,
                    range_name=f"{start_range}:{end_range}",
                    value_input_option='RAW'
                )
                
                # Batch format all columns in a single API call
                batch_format_columns(
                    matched_sheet,
                    date_ranges=[f'B{next_row}:B{next_row + len(matched_rows) - 1}'],
                    date_mmyyyy_ranges=[f'C{next_row}:C{next_row + len(matched_rows) - 1}'],
                    text_ranges=[f'E{next_row}:E{next_row + len(matched_rows) - 1}'],
                    number_ranges={
                        f'F{next_row}:F{next_row + len(matched_rows) - 1}': '#,##0.00',
                        f'G{next_row}:G{next_row + len(matched_rows) - 1}': '#,##0.00'
                    }
                )
                
                logger.info(f"   ✅ Appended {len(matched_rows)} transactions to 'Matched' sheet (rows {next_row}-{next_row + len(matched_rows) - 1})")
            
            # Remove matched rows from Unmatched sheet
            logger.info("   • Updating 'Unmatched' sheet...")
            remaining_rows = [data[0]]  # Keep header
            for i, row in enumerate(data[1:], 1):
                if i not in matched_indices:
                    remaining_rows.append(row)
            
            # Process rows to format Column B dates
            remaining_rows = convert_column_b_to_serial(remaining_rows)
            
            # Clear ALL data and formatting (removes old highlight colors)
            unmatched_sheet.clear()
            
            # Also clear all cell formatting explicitly to remove colors
            try:
                # Clear background colors for all cells
                clear_format_request = {
                    'requests': [{
                        'repeatCell': {
                            'range': {
                                'sheetId': unmatched_sheet.id,
                            },
                            'cell': {
                                'userEnteredFormat': {
                                    'backgroundColor': {
                                        'red': 1.0,
                                        'green': 1.0,
                                        'blue': 1.0
                                    }
                                }
                            },
                            'fields': 'userEnteredFormat.backgroundColor'
                        }
                    }]
                }
                self.workbook.batch_update(clear_format_request)
            except Exception as e:
                logger.warning(f"   ⚠️  Could not clear cell formatting: {e}")
            
            # Skip writing data here - let re-application handle it to avoid flashing
            logger.info(f"   ✅ Prepared {len(remaining_rows)-1} remaining transactions for re-processing")

            # Re-apply suggestive matching to remaining transactions
            logger.info("\n" + "="*60)
            logger.info("🔄 RE-APPLYING SUGGESTIVE MATCHING TO REMAINING TRANSACTIONS")
            logger.info("="*60)
            
            # Use the prepared remaining_rows data directly instead of re-reading
            if len(remaining_rows) > 1:
                # Re-run Phase 4 steps on remaining data
                logger.info(f"   Processing {len(remaining_rows)-1} remaining transactions...")
                
                # STEP 1: Sort by GL then Date
                sorted_data = self._initial_sort_unmatched(remaining_rows)
                
                # STEP 2: Find suggested matches
                match_data = self._find_suggestive_matches(sorted_data)
                
                # STEP 3: Priority re-sorting
                final_sorted_data = self._sort_by_priority_with_suggestions(sorted_data, match_data)
                
                # STEP 4: Write sorted data
                self._write_sorted_data_to_unmatched(unmatched_sheet, final_sorted_data)
                
                # STEP 5: Apply colors
                self._apply_colors_to_matches(unmatched_sheet, sorted_data, final_sorted_data, match_data)
                
                logger.info(f"   ✅ Updated 'Unmatched' sheet: {len(data)-1} → {len(remaining_rows)-1} transactions")
                logger.info(f"      (Removed {len(matched_rows)} transactions, {len(remaining_rows)-1} remaining)")
                logger.info("   ✅ Suggestive matching re-applied - check 'Unmatched' sheet for new highlights")
            else:
                logger.info("   ℹ️  No remaining transactions to highlight")

            
        except Exception as e:
            logger.error(f"   ❌ Error processing Phase 4 matches: {e}")
            import traceback
            traceback.print_exc()

    def _run_phase5(self) -> None:
        """Phase 5: Generate subsidiary ledger T-accounts"""
        logger.info("\n" + "="*60)
        logger.info("🔄 Phase 5: Generating Subsidiary Ledger T-Accounts")
        logger.info("="*60)
        
        try:
            # Read Unmatched sheet data
            unmatched_sheet = self.workbook.worksheet(UNMATCHED_SHEET_NAME)
            data = unmatched_sheet.get(value_render_option='UNFORMATTED_VALUE')
            
            if len(data) <= 1:
                logger.info("  ℹ️  No unmatched transactions to process in Phase 5")
                return
            
            logger.info(f"  📊 Processing {len(data)-1} transactions for subsidiary ledgers...")
            
            # Read owner group properties from main sheet Column V
            main_sheet = self.workbook.worksheet(SOURCE_SHEET_NAME)
            owner_group_data = main_sheet.get('V2:V', value_render_option='UNFORMATTED_VALUE')
            owner_group_properties = set(safe_str(row[0]).strip().lower() for row in owner_group_data if row and row[0])
            logger.info(f"  📋 Loaded {len(owner_group_properties)} properties in owner group")
            
            # Group transactions by subsidiary ledger (Column N) and GL (Column A)
            header = data[0]
            transactions = data[1:]
            
            logger.info(f"  📋 Analyzing {len(transactions)} transactions...")
            
            # Data structure: {subsidiary_ledger: {gl: [transactions]}}
            ledger_groups = {}
            skipped_count = 0
            
            for row in transactions:
                if len(row) <= 13:  # Need at least up to Column N (index 13)
                    skipped_count += 1
                    continue
                    
                gl = safe_str(row[0]) if len(row) > 0 else ""  # Column A
                subsidiary_ledger = safe_str(row[13]) if len(row) > 13 else ""  # Column N
                property_code = safe_str(row[9]).strip().lower() if len(row) > 9 else ""  # Column J
                
                if not subsidiary_ledger:
                    skipped_count += 1
                    continue
                
                # Determine if this belongs to SL 1 or SL 2
                in_owner_group = property_code in owner_group_properties
                
                # Create ledger entry
                if subsidiary_ledger not in ledger_groups:
                    ledger_groups[subsidiary_ledger] = {
                        'gl': gl,
                        'in_owner_group': in_owner_group,
                        'debits': [],
                        'credits': []
                    }
                
                # Extract transaction data
                date_val = row[1] if len(row) > 1 else ""  # Column B
                description = safe_str(row[3]) if len(row) > 3 else ""  # Column D
                debit = 0.0
                credit = 0.0
                
                # Parse debit (Column F)
                if len(row) > 5 and row[5]:
                    try:
                        if isinstance(row[5], (int, float)):
                            debit = float(row[5])
                        else:
                            debit_str = str(row[5]).strip().replace(',', '').replace('$', '')
                            if debit_str:
                                debit = float(debit_str)
                    except (ValueError, TypeError):
                        debit = 0.0
                
                # Parse credit (Column G)
                if len(row) > 6 and row[6]:
                    try:
                        if isinstance(row[6], (int, float)):
                            credit = float(row[6])
                        else:
                            credit_str = str(row[6]).strip().replace(',', '').replace('$', '')
                            if credit_str:
                                credit = float(credit_str)
                    except (ValueError, TypeError):
                        credit = 0.0
                
                # Add to appropriate side
                if debit > 0:
                    ledger_groups[subsidiary_ledger]['debits'].append({
                        'date': date_val,
                        'description': description,
                        'amount': debit
                    })
                
                if credit > 0:
                    ledger_groups[subsidiary_ledger]['credits'].append({
                        'date': date_val,
                        'description': description,
                        'amount': credit
                    })
            
            logger.info(f"  📊 Processed {len(ledger_groups)} subsidiary ledgers ({skipped_count} transactions skipped - no subsidiary ledger in Column N)")
            
            # Separate into SL 1 and SL 2
            sl1_ledgers = {}  # {gl: [ledgers]}
            sl2_ledgers = {}  # {gl: [ledgers]}
            
            for subsidiary_ledger, ledger_data in ledger_groups.items():
                gl = ledger_data['gl']
                target_dict = sl2_ledgers if ledger_data['in_owner_group'] else sl1_ledgers
                
                if gl not in target_dict:
                    target_dict[gl] = []
                target_dict[gl].append({
                    'name': subsidiary_ledger,
                    'debits': ledger_data['debits'],
                    'credits': ledger_data['credits']
                })
            
            logger.info(f"  📊 SL 1 (External): {sum(len(ledgers) for ledgers in sl1_ledgers.values())} ledgers across {len(sl1_ledgers)} GL codes")
            logger.info(f"  📊 SL 2 (Internal): {sum(len(ledgers) for ledgers in sl2_ledgers.values())} ledgers across {len(sl2_ledgers)} GL codes")
            
            # Generate sheets and collect ending balance data
            sl1_summary_data = self._generate_subsidiary_ledger_sheet("SL 1", sl1_ledgers)
            sl2_summary_data = self._generate_subsidiary_ledger_sheet("SL 2", sl2_ledgers)
            
            # Generate SL Summary sheet
            self._generate_sl_summary_sheet(sl1_summary_data, sl2_summary_data)
            
            logger.info("📊 Phase 5 complete")
            
        except Exception as e:
            logger.error(f"❌ Error in Phase 5: {e}")
            import traceback
            traceback.print_exc()
    
    def _generate_subsidiary_ledger_sheet(self, sheet_name: str, gl_ledgers: dict) -> list:
        """Generate T-account layout for subsidiary ledgers"""
        logger.info(f"\n📝 Generating {sheet_name}...")
        
        try:
            # Get or create sheet
            try:
                sheet = self.workbook.worksheet(sheet_name)
                
                # Clear content
                sheet.clear()
                
                # Unmerge all cells in the sheet using batch_update
                try:
                    self.workbook.batch_update({
                        'requests': [{
                            'unmergeCells': {
                                'range': {
                                    'sheetId': sheet.id
                                }
                            }
                        }]
                    })
                except Exception as e:
                    # Ignore error if there are no merged cells
                    if 'no merged cells' not in str(e).lower():
                        logger.warning(f"   ⚠️  Could not unmerge cells: {e}")
                
                # Clear formatting by updating ALL columns (not just A:Z)
                # Format entire sheet to remove all borders and formatting
                sheet.format('1:1000', {  # Format first 1000 rows across all columns
                    'borders': {},
                    'textFormat': {'bold': False, 'italic': False},
                    'horizontalAlignment': 'LEFT',
                    'numberFormat': {'type': 'TEXT'}
                })
                logger.info(f"   ✅ Cleared existing {sheet_name} (content + formatting + merged cells)")
            except:
                sheet = self.workbook.add_worksheet(title=sheet_name, rows=1000, cols=26)
                logger.info(f"   ✅ Created new {sheet_name}")
            
            if not gl_ledgers:
                logger.info(f"   ℹ️  No ledgers for {sheet_name}")
                return
            
            all_data = []
            current_row = 0
            current_col = 0
            
            # Sort GL codes for consistent layout
            sorted_gls = sorted(gl_ledgers.keys())
            
            logger.info(f"   📊 Processing {len(sorted_gls)} GL codes...")
            
            # Track balance sides for formatting AND collect summary data
            ledger_balance_sides = {}  # {(gl, ledger_idx): 'debit' or 'credit'}
            summary_data = []  # [(name, ending_balance, balance_side), ...] in left→down→right→down order
            
            for gl_idx, gl in enumerate(sorted_gls):
                ledgers = gl_ledgers[gl]
                logger.info(f"      GL: {gl} - {len(ledgers)} ledgers")
                
                # Stack vertically within same GL
                for ledger_idx, ledger in enumerate(ledgers):
                    logger.info(f"         • {ledger['name']} - {max(len(ledger['debits']), len(ledger['credits'])) + 5} rows")
                    
                    # Add blank row between ledgers (except first)
                    if ledger_idx > 0:
                        current_row += 1
                    
                    # Generate T-account for this ledger
                    t_account_data, height, balance_side = self._create_t_account(gl, ledger)
                    
                    # Store balance side for formatting
                    ledger_balance_sides[(gl, ledger_idx)] = balance_side
                    
                    # Calculate ending balance for summary (with sign: debit=-ve, credit=+ve)
                    debit_total = sum(d['amount'] for d in ledger['debits'])
                    credit_total = sum(c['amount'] for c in ledger['credits'])
                    ending_balance, _ = self._calculate_ending_balance(debit_total, credit_total)
                    
                    # Apply sign: debit = negative, credit = positive
                    if balance_side == 'debit':
                        signed_balance = -ending_balance
                    else:  # credit
                        signed_balance = ending_balance
                    
                    # Add to summary data in order (left→down→right→down)
                    summary_data.append((ledger['name'], signed_balance, balance_side))
                    
                    # Place data in grid
                    for row_offset, row_data in enumerate(t_account_data):
                        row_num = current_row + row_offset
                        while len(all_data) <= row_num:
                            all_data.append([])
                        
                        # Ensure row has enough columns
                        while len(all_data[row_num]) < current_col:
                            all_data[row_num].append('')
                        
                        # Add row data
                        all_data[row_num].extend(row_data)
                    
                    current_row += height
                
                # Move to next GL horizontally (add blank column + reset row)
                if gl_idx < len(sorted_gls) - 1:
                    current_col += 7  # 6 columns + 1 blank
                    current_row = 0
            
            # Write to sheet
            if all_data:
                sheet.update(all_data, value_input_option='USER_ENTERED')
                logger.info(f"   ✅ Written {len(all_data)} rows to {sheet_name}")
                
                # Apply formatting (pass balance sides)
                self._apply_t_account_formatting(sheet, gl_ledgers, current_col, ledger_balance_sides)
                logger.info(f"   ✅ Applied formatting to {sheet_name}")
            
            # Return summary data for SL Summary sheet
            return summary_data
            
        except Exception as e:
            logger.error(f"   ❌ Error generating {sheet_name}: {e}")
            import traceback
            traceback.print_exc()
            return []  # Return empty list on error
    
    def _generate_sl_summary_sheet(self, sl1_data: list, sl2_data: list) -> None:
        """
        Generate SL Summary sheet with SL 1 and SL 2 ending balances
        
        Args:
            sl1_data: [(name, signed_balance, balance_side), ...] for SL 1
            sl2_data: [(name, signed_balance, balance_side), ...] for SL 2
        """
        logger.info(f"\n📝 Generating SL Summary sheet...")
        
        try:
            # Get or create sheet
            try:
                sheet = self.workbook.worksheet("SL Summary")
                
                # Clear content
                sheet.clear()
                
                # Unmerge all cells in the sheet using batch_update
                try:
                    self.workbook.batch_update({
                        'requests': [{
                            'unmergeCells': {
                                'range': {
                                    'sheetId': sheet.id
                                }
                            }
                        }]
                    })
                except Exception as e:
                    # Ignore error if there are no merged cells
                    if 'no merged cells' not in str(e).lower():
                        logger.warning(f"   ⚠️  Could not unmerge cells: {e}")
                
                # Clear formatting by updating ALL columns (same as SL 1/SL 2)
                sheet.format('1:100', {  # Format first 100 rows across all columns
                    'borders': {},
                    'textFormat': {'bold': False, 'italic': False},
                    'horizontalAlignment': 'LEFT',
                    'numberFormat': {'type': 'TEXT'}
                })
                logger.info(f"   ✅ Cleared existing SL Summary (content + formatting + merged cells)")
            except:
                sheet = self.workbook.add_worksheet(title="SL Summary", rows=100, cols=10)
                logger.info(f"   ✅ Created new SL Summary")
            
            logger.info(f"   📊 SL 1: {len(sl1_data)} ledgers")
            logger.info(f"   📊 SL 2: {len(sl2_data)} ledgers")
            
            # Read unique property codes (GL codes) from main sheet (Column A)
            # We'll create SUM formulas to aggregate balances from Column K for each GL
            main_sheet = self.workbook.worksheet(SOURCE_SHEET_NAME)
            main_data = main_sheet.get('A:A', value_render_option='UNFORMATTED_VALUE')
            
            # Extract unique property codes from Column A (skip header and empty cells)
            property_codes = []
            seen_properties = set()
            for i, row in enumerate(main_data):
                if i == 0:  # Skip header row
                    continue
                if len(row) > 0 and row[0]:
                    property_code = safe_str(row[0])
                    if property_code and property_code.lower() not in ['gl', 'property', '']:
                        if property_code not in seen_properties:
                            property_codes.append(property_code)
                            seen_properties.add(property_code)
            
            # Sort property codes alphabetically for consistent display
            property_codes.sort()
            
            logger.info(f"   📊 Property Codes: {len(property_codes)} unique GL codes from main sheet")
            
            # Prepare data structure
            all_data = []
            
            # Row 1: Headers (SL 1, SL 2, and Property headers)
            all_data.append(['SL 1', '', '', 'SL 2', '', '', '', '', '', 'Property', 'Actual Balance'])
            
            # Calculate last data row for each section (row 1 is header, data starts at row 2)
            sl1_last_data_row = len(sl1_data) + 1  # +1 for header row
            sl2_last_data_row = len(sl2_data) + 1  # +1 for header row
            property_last_data_row = len(property_codes) + 1  # +1 for header row
            
            # Calculate TOTAL row positions
            sl1_total_row = sl1_last_data_row + 1  # Right after SL 1 data
            sl2_total_row = sl2_last_data_row + 1  # Right after SL 2 data
            property_total_row = property_last_data_row + 1  # Right after property data
            
            # Determine how many rows we need total (use the max of all sections)
            max_rows = max(sl1_total_row, sl2_total_row, property_total_row)
            
            # Build data row by row (starting from index 1 since row 0 is already header)
            for i in range(1, max_rows):  # Start from 1 since row 0 is header
                row = ['', '', '', '', '', '', '', '', '', '', '']  # A through K (11 columns)
                
                # SL 1 side (A-B) - data starts at row 2 (index 1)
                if i <= len(sl1_data):  # Data rows
                    name, balance, _ = sl1_data[i - 1]
                    row[0] = name  # Column A
                    row[1] = balance  # Column B
                elif i == sl1_total_row - 1:  # TOTAL row (convert to 0-indexed)
                    row[0] = 'TOTAL'
                    row[1] = f'=SUM(B2:B{sl1_last_data_row})'
                
                # SL 2 side (D-E) - data starts at row 2 (index 1)
                if i <= len(sl2_data):  # Data rows
                    name, balance, _ = sl2_data[i - 1]
                    row[3] = name  # Column D
                    row[4] = balance  # Column E
                elif i == sl2_total_row - 1:  # TOTAL row (convert to 0-indexed)
                    row[3] = 'TOTAL'
                    row[4] = f'=SUM(E2:E{sl2_last_data_row})'
                
                # Property balances (J-K) - data starts at row 2 (index 1)
                if i <= len(property_codes):  # Data rows
                    prop_code = property_codes[i - 1]
                    row[9] = prop_code  # Column J
                    # Create formula to sum (Column G - Column F) for each GL code
                    # Balance = SUMIF for Credits (Column G) - SUMIF for Debits (Column F)
                    # Formula: =SUMIF(A:A,"gl_code",G:G)-SUMIF(A:A,"gl_code",F:F)
                    row[10] = f'=SUMIF(\'{SOURCE_SHEET_NAME}\'!A:A,"{prop_code}",\'{SOURCE_SHEET_NAME}\'!G:G)-SUMIF(\'{SOURCE_SHEET_NAME}\'!A:A,"{prop_code}",\'{SOURCE_SHEET_NAME}\'!F:F)'
                elif i == property_total_row - 1:  # TOTAL row for property balances
                    row[9] = ''  # No label, just the sum
                    row[10] = f'=SUM(K2:K{property_last_data_row})'
                
                all_data.append(row)
            
            # Add 2 blank rows before summary section
            all_data.append(['', '', '', '', '', '', '', '', '', '', ''])
            all_data.append(['', '', '', '', '', '', '', '', '', '', ''])
            
            # Summary section (G3:H5)
            summary_start_row = max_rows + 3  # Row number for "SL 1 Total"
            
            # Update row 3 for summary (need to ensure row 3 exists)
            while len(all_data) < 3:
                all_data.append([])
            
            # Ensure row 3 has enough columns
            while len(all_data[2]) < 8:
                all_data[2].append('')
            
            # Add summary data to row 3 (index 2)
            all_data[2][6] = 'SL 1 Total'  # Column G
            all_data[2][7] = f'=B{sl1_total_row}'  # Column H
            
            # Row 4 - SL 2 Total
            while len(all_data) < 4:
                all_data.append([])
            while len(all_data[3]) < 8:
                all_data[3].append('')
            
            all_data[3][6] = 'SL 2 Total'  # Column G
            all_data[3][7] = f'=E{sl2_total_row}'  # Column H
            
            # Row 5 - Grand Total (Column G is silent/empty)
            while len(all_data) < 5:
                all_data.append([])
            while len(all_data[4]) < 8:
                all_data[4].append('')
            
            all_data[4][6] = ''  # Column G (silent)
            all_data[4][7] = '=H3+H4'  # Column H - Grand Total
            
            # Write to sheet
            sheet.update(all_data, value_input_option='USER_ENTERED')
            logger.info(f"   ✅ Written {len(all_data)} rows to SL Summary")
            
            # Auto-resize columns to fit data with minimum width of 100 pixels
            # Use autoResizeDimensions API with dimensionRange to set bounds
            body = {'requests': []}
            
            for col_index in range(11):  # Columns 0-10 (A through K)
                body['requests'].append({
                    'autoResizeDimensions': {
                        'dimensions': {
                            'sheetId': sheet.id,
                            'dimension': 'COLUMNS',
                            'startIndex': col_index,
                            'endIndex': col_index + 1
                        }
                    }
                })
            
            # Execute auto-resize
            self.workbook.batch_update(body)
            
            # Now get the current column widths after auto-resize
            time.sleep(1)  # Brief pause to ensure auto-resize completes
            sheet_metadata = self.workbook.fetch_sheet_metadata({'includeGridData': True})
            current_widths = {}
            
            for sheet_info in sheet_metadata['sheets']:
                if sheet_info['properties']['title'] == 'SL Summary':
                    if 'data' in sheet_info and len(sheet_info['data']) > 0:
                        grid_data = sheet_info['data'][0]
                        if 'columnMetadata' in grid_data:
                            for idx, col_meta in enumerate(grid_data['columnMetadata']):
                                pixel_size = col_meta.get('pixelSize', 100)
                                current_widths[idx] = pixel_size
                    break
            
            # Apply minimum width of 100 pixels only to columns narrower than 100
            body = {'requests': []}
            for col_index in range(11):  # Columns 0-10 (A through K)
                current_width = current_widths.get(col_index, 0)
                if current_width < 100:
                    body['requests'].append({
                        'updateDimensionProperties': {
                            'range': {
                                'sheetId': sheet.id,
                                'dimension': 'COLUMNS',
                                'startIndex': col_index,
                                'endIndex': col_index + 1
                            },
                            'properties': {
                                'pixelSize': 100
                            },
                            'fields': 'pixelSize'
                        }
                    })
            
            if body['requests']:
                self.workbook.batch_update(body)
                logger.info(f"   ✅ Auto-resized columns (minimum 100 pixels applied to {len(body['requests'])} columns)")
            else:
                logger.info(f"   ✅ Auto-resized columns (all columns already >= 100 pixels)")
            
            # Apply formatting (pass all section parameters)
            self._format_sl_summary_sheet(sheet, sl1_total_row, sl2_total_row, sl1_last_data_row, sl2_last_data_row, 
                                          property_last_data_row, property_total_row)
            logger.info(f"   ✅ Applied formatting to SL Summary")
            
        except Exception as e:
            logger.error(f"   ❌ Error generating SL Summary: {e}")
            import traceback
            traceback.print_exc()
    
    def _format_sl_summary_sheet(self, sheet, sl1_total_row: int, sl2_total_row: int, sl1_last_data_row: int, sl2_last_data_row: int, 
                                  property_last_data_row: int, property_total_row: int) -> None:
        """Apply formatting to SL Summary sheet"""
        format_requests = []
        
        # 1. Merge and center headers (Row 1)
        try:
            sheet.merge_cells('A1:B1')  # SL 1
            sheet.merge_cells('D1:E1')  # SL 2
        except Exception as e:
            logger.warning(f"   ⚠️ Could not merge header cells: {e}")
        
        # Bold and center all headers in Row 1 (A1:B1, D1:E1, J1:K1)
        format_requests.append({
            'range': 'A1:B1',
            'format': {
                'horizontalAlignment': 'CENTER',
                'textFormat': {'bold': True}
            }
        })
        format_requests.append({
            'range': 'D1:E1',
            'format': {
                'horizontalAlignment': 'CENTER',
                'textFormat': {'bold': True}
            }
        })
        format_requests.append({
            'range': 'J1:K1',
            'format': {
                'horizontalAlignment': 'CENTER',
                'textFormat': {'bold': True}
            }
        })
        
        # 2. Format data rows (A2:B and D2:E)
        # Number format for SL 1 balance column
        format_requests.append({
            'range': f'B2:B{sl1_last_data_row}',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT'
            }
        })
        # Number format for SL 2 balance column
        format_requests.append({
            'range': f'E2:E{sl2_last_data_row}',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT'
            }
        })
        
        # 3. Thick line at bottom of last data row for each section
        # SL 1 thick line
        format_requests.append({
            'range': f'A{sl1_last_data_row}:B{sl1_last_data_row}',
            'format': {
                'borders': {
                    'bottom': {'style': 'SOLID_THICK'}
                }
            }
        })
        # SL 2 thick line
        format_requests.append({
            'range': f'D{sl2_last_data_row}:E{sl2_last_data_row}',
            'format': {
                'borders': {
                    'bottom': {'style': 'SOLID_THICK'}
                }
            }
        })
        
        # 4. Bold text for TOTAL rows
        format_requests.append({
            'range': f'A{sl1_total_row}:B{sl1_total_row}',
            'format': {
                'textFormat': {'bold': True}
            }
        })
        format_requests.append({
            'range': f'D{sl2_total_row}:E{sl2_total_row}',
            'format': {
                'textFormat': {'bold': True}
            }
        })
        
        # 5. Red double-line below TOTAL amounts (B and E only)
        format_requests.append({
            'range': f'B{sl1_total_row}',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT',
                'textFormat': {'bold': True},
                'borders': {
                    'bottom': {
                        'style': 'DOUBLE',
                        'width': 3,
                        'color': {'red': 1.0, 'green': 0.0, 'blue': 0.0}
                    }
                }
            }
        })
        format_requests.append({
            'range': f'E{sl2_total_row}',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT',
                'textFormat': {'bold': True},
                'borders': {
                    'bottom': {
                        'style': 'DOUBLE',
                        'width': 3,
                        'color': {'red': 1.0, 'green': 0.0, 'blue': 0.0}
                    }
                }
            }
        })
        
        # 5. Summary section formatting (G3:H5)
        # Row 3 - SL 1 Total
        format_requests.append({
            'range': 'H3',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT'
            }
        })
        
        # Row 4 - SL 2 Total with thick line below
        format_requests.append({
            'range': 'H4',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT',
                'borders': {
                    'bottom': {'style': 'SOLID_THICK'}
                }
            }
        })
        
        # Row 5 - Grand Total with red double-line below
        format_requests.append({
            'range': 'H5',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT',
                'textFormat': {'bold': True},
                'borders': {
                    'bottom': {
                        'style': 'DOUBLE',
                        'width': 3,
                        'color': {'red': 1.0, 'green': 0.0, 'blue': 0.0}
                    }
                }
            }
        })
        
        # 6. Property balance section formatting (J-K)
        # Property balance data (K2:K{property_last_data_row}) - number format
        format_requests.append({
            'range': f'K2:K{property_last_data_row}',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT'
            }
        })
        
        # Thick border at bottom of last property data row
        format_requests.append({
            'range': f'J{property_last_data_row}:K{property_last_data_row}',
            'format': {
                'borders': {
                    'bottom': {'style': 'SOLID_THICK'}
                }
            }
        })
        
        # Property total row (K only) - red double-line below
        format_requests.append({
            'range': f'K{property_total_row}',
            'format': {
                'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                'horizontalAlignment': 'RIGHT',
                'textFormat': {'bold': True},
                'borders': {
                    'bottom': {
                        'style': 'DOUBLE',
                        'width': 3,
                        'color': {'red': 1.0, 'green': 0.0, 'blue': 0.0}
                    }
                }
            }
        })
        
        # Apply all formatting
        if format_requests:
            sheet.batch_format(format_requests)
    
    def _create_t_account(self, gl: str, ledger: dict) -> tuple:
        """Create T-account data structure for a single ledger"""
        name = ledger['name']  # This already contains "gl - subsidiary" from Column N
        debits = sorted(ledger['debits'], key=lambda x: x['date'])
        credits = sorted(ledger['credits'], key=lambda x: x['date'])
        
        # Calculate totals
        debit_total = sum(d['amount'] for d in debits)
        credit_total = sum(c['amount'] for c in credits)
        
        # Create header - Only show Column N value (already has "GL - Subsidiary Ledger")
        data = []
        data.append([name, '', '', '', '', ''])  # Header row (will be italicized and merged)
        data.append(['Date', 'Description', 'Debit', 'Credit', 'Description', 'Date'])  # Column headers
        
        # Determine max rows
        max_rows = max(len(debits), len(credits))
        
        # Add transaction rows
        for i in range(max_rows):
            row = []
            
            # Debit side (left)
            if i < len(debits):
                row.extend([
                    debits[i]['date'],
                    debits[i]['description'],
                    debits[i]['amount']
                ])
            else:
                row.extend(['', '', ''])
            
            # Credit side (right)
            if i < len(credits):
                row.extend([
                    credits[i]['amount'],
                    credits[i]['description'],
                    credits[i]['date']
                ])
            else:
                row.extend(['', '', ''])
            
            data.append(row)
        
        # Add total row immediately after last transaction (will be bolded) - NO colon after TOTAL
        data.append(['', 'TOTAL', debit_total, credit_total, 'TOTAL', ''])
        
        # Calculate and add ending balance row
        ending_balance, balance_side = self._calculate_ending_balance(debit_total, credit_total)
        
        # Add ending balance row (blank except for the balance amount in appropriate column)
        if balance_side == 'debit':
            data.append(['', '', ending_balance, '', '', ''])  # Show in Debit column
        else:  # balance_side == 'credit'
            data.append(['', '', '', ending_balance, '', ''])  # Show in Credit column
        
        # Add 1 empty row after ending balance (for vertical separator continuation)
        data.append(['', '', '', '', '', ''])
        
        return data, len(data), balance_side  # Return balance_side for formatting
    
    def _calculate_ending_balance(self, debit_total: float, credit_total: float) -> tuple:
        """
        Calculate ending balance based on debit and credit totals
        
        Logic:
        - If one side is zero: Ending balance = non-zero side (no subtraction)
        - If both have values: Ending balance = |greater - smaller|, displayed on greater side
        
        Returns:
            (ending_balance_amount, 'debit' or 'credit')
        """
        # Situation 1: Credit is zero
        if credit_total == 0:
            return (debit_total, 'debit')
        
        # Situation 2: Debit is zero
        if debit_total == 0:
            return (credit_total, 'credit')
        
        # Situation 3: Both sides have values - calculate difference
        if debit_total > credit_total:
            return (debit_total - credit_total, 'debit')
        else:  # credit_total > debit_total
            return (credit_total - debit_total, 'credit')

    def _apply_t_account_formatting(self, sheet, gl_ledgers: dict, total_cols: int, ledger_balance_sides: dict) -> None:
        """Apply all formatting to T-accounts using batch formatting"""
        
        def col_letter(col_index):
            """Convert 0-based column index to Excel column letter (A, B, ..., Z, AA, AB, ...)"""
            result = ""
            while col_index >= 0:
                result = chr(65 + (col_index % 26)) + result
                col_index = col_index // 26 - 1
            return result
        
        sorted_gls = sorted(gl_ledgers.keys())
        current_col = 0
        
        # Collect all format requests to batch
        format_requests = []
        merge_requests = []
        
        for gl_idx, gl in enumerate(sorted_gls):
            ledgers = gl_ledgers[gl]
            current_row = 0
            
            for ledger_idx, ledger in enumerate(ledgers):
                # Add blank row between ledgers (except first)
                if ledger_idx > 0:
                    current_row += 1
                
                # Calculate ranges
                start_row = current_row + 1  # 1-indexed
                header_row = start_row
                column_header_row = start_row + 1
                data_start_row = start_row + 2
                
                max_rows = max(len(ledger['debits']), len(ledger['credits']))
                data_end_row = data_start_row + max_rows - 1
                total_row = data_end_row + 1  # Immediately after last transaction
                ending_balance_row = total_row + 1  # Row after TOTAL (for ending balance)
                separator_end_row = total_row + 2  # Extends 1 row after ending balance
                
                # Column letters using proper conversion
                col_a = col_letter(current_col)      # A, H, O, V, AC, etc.
                col_b = col_letter(current_col + 1)
                col_c = col_letter(current_col + 2)
                col_d = col_letter(current_col + 3)
                col_e = col_letter(current_col + 4)
                col_f = col_letter(current_col + 5)
                
                # 1. Header row (italicized, merged, centered) + border below
                merge_requests.append(f'{col_a}{header_row}:{col_f}{header_row}')
                format_requests.append({
                    'range': f'{col_a}{header_row}:{col_f}{header_row}',
                    'format': {
                        'textFormat': {'italic': True},
                        'horizontalAlignment': 'CENTER',
                        'borders': {
                            'bottom': {'style': 'SOLID', 'width': 1}
                        }
                    }
                })
                
                # 2. Column headers (center-aligned)
                format_requests.append({
                    'range': f'{col_a}{column_header_row}:{col_f}{column_header_row}',
                    'format': {
                        'horizontalAlignment': 'CENTER',
                        'textFormat': {'bold': False}
                    }
                })
                
                # 3. Middle vertical separator (Column C/D border) - extends through TOTAL + 2 rows after
                format_requests.append({
                    'range': f'{col_c}{column_header_row}:{col_c}{separator_end_row}',
                    'format': {
                        'borders': {
                            'right': {'style': 'SOLID', 'width': 1}
                        }
                    }
                })
                
                # 4. Date columns (A and F) - center-aligned with date format
                if data_start_row <= data_end_row:
                    format_requests.append({
                        'range': f'{col_a}{data_start_row}:{col_a}{data_end_row}',
                        'format': {
                            'numberFormat': {'type': 'DATE', 'pattern': 'mm/dd/yyyy'},
                            'horizontalAlignment': 'CENTER'
                        }
                    })
                    format_requests.append({
                        'range': f'{col_f}{data_start_row}:{col_f}{data_end_row}',
                        'format': {
                            'numberFormat': {'type': 'DATE', 'pattern': 'mm/dd/yyyy'},
                            'horizontalAlignment': 'CENTER'
                        }
                    })
                    
                    # 5. Description columns (B and E) - left-aligned
                    format_requests.append({
                        'range': f'{col_b}{data_start_row}:{col_b}{data_end_row}',
                        'format': {'horizontalAlignment': 'LEFT'}
                    })
                    format_requests.append({
                        'range': f'{col_e}{data_start_row}:{col_e}{data_end_row}',
                        'format': {'horizontalAlignment': 'LEFT'}
                    })
                    
                    # 6. Amount columns (C and D) - right-aligned with comma format
                    format_requests.append({
                        'range': f'{col_c}{data_start_row}:{col_c}{data_end_row}',
                        'format': {
                            'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                            'horizontalAlignment': 'RIGHT'
                        }
                    })
                    format_requests.append({
                        'range': f'{col_d}{data_start_row}:{col_d}{data_end_row}',
                        'format': {
                            'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                            'horizontalAlignment': 'RIGHT'
                        }
                    })
                
                # 7. TOTAL row - normal line on top + thick single line on bottom + bold text + number format
                # Apply top and bottom borders to entire row first
                format_requests.append({
                    'range': f'{col_a}{total_row}:{col_f}{total_row}',
                    'format': {
                        'borders': {
                            'top': {'style': 'SOLID', 'width': 1},  # Normal line above TOTAL
                            'bottom': {'style': 'SOLID_THICK'}  # Thick single line below TOTAL
                        }
                    }
                })
                
                # Format TOTAL text (Column B and E)
                format_requests.append({
                    'range': f'{col_b}{total_row}',
                    'format': {
                        'textFormat': {'bold': True},
                        'horizontalAlignment': 'LEFT'
                    }
                })
                format_requests.append({
                    'range': f'{col_e}{total_row}',
                    'format': {
                        'textFormat': {'bold': True},
                        'horizontalAlignment': 'LEFT'
                    }
                })
                
                # Format Debit total (Column C) - with middle separator
                format_requests.append({
                    'range': f'{col_c}{total_row}',
                    'format': {
                        'textFormat': {'bold': True},
                        'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                        'horizontalAlignment': 'RIGHT',
                        'borders': {
                            'top': {'style': 'SOLID', 'width': 1},  # Ensure top border
                            'right': {'style': 'SOLID', 'width': 1},  # Middle separator
                            'bottom': {'style': 'SOLID_THICK'}  # Thick single line
                        }
                    }
                })
                
                # Format Credit total (Column D) - ensure top border is included
                format_requests.append({
                    'range': f'{col_d}{total_row}',
                    'format': {
                        'textFormat': {'bold': True},
                        'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                        'horizontalAlignment': 'RIGHT',
                        'borders': {
                            'top': {'style': 'SOLID', 'width': 1},  # FIX: Add top border
                            'bottom': {'style': 'SOLID_THICK'}  # Thick single line
                        }
                    }
                })
                
                # 8. Ending balance row - format amount columns with number format and red double-line
                # Get which side has the balance for this ledger
                balance_side = ledger_balance_sides.get((gl, ledger_idx), 'debit')
                
                # Format Debit ending balance cell (Column C)
                if balance_side == 'debit':
                    # This cell has the ending balance - add red double-line border
                    format_requests.append({
                        'range': f'{col_c}{ending_balance_row}',
                        'format': {
                            'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                            'horizontalAlignment': 'RIGHT',
                            'borders': {
                                'right': {'style': 'SOLID', 'width': 1},  # Middle separator
                                'bottom': {
                                    'style': 'DOUBLE',
                                    'width': 3,
                                    'color': {'red': 1.0, 'green': 0.0, 'blue': 0.0}
                                }
                            }
                        }
                    })
                else:
                    # This cell is empty - just maintain middle separator
                    format_requests.append({
                        'range': f'{col_c}{ending_balance_row}',
                        'format': {
                            'borders': {
                                'right': {'style': 'SOLID', 'width': 1}  # Middle separator
                            }
                        }
                    })
                
                # Format Credit ending balance cell (Column D)
                if balance_side == 'credit':
                    # This cell has the ending balance - add red double-line border
                    format_requests.append({
                        'range': f'{col_d}{ending_balance_row}',
                        'format': {
                            'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0.00'},
                            'horizontalAlignment': 'RIGHT',
                            'borders': {
                                'bottom': {
                                    'style': 'DOUBLE',
                                    'width': 3,
                                    'color': {'red': 1.0, 'green': 0.0, 'blue': 0.0}
                                }
                            }
                        }
                    })
                else:
                    # This cell is empty - no special formatting needed
                    pass
                
                # Update current row for next ledger (header + column header + data + TOTAL + 2 empty rows)
                current_row += (separator_end_row - start_row + 1)
            
            # Move to next GL horizontally
            if gl_idx < len(sorted_gls) - 1:
                current_col += 7  # 6 columns + 1 blank
        
        # Apply all merge requests (one at a time due to gspread API)
        for merge_range in merge_requests:
            try:
                sheet.merge_cells(merge_range)
            except Exception as e:
                logger.error(f"Error merging cells {merge_range}: {e}")
        
        # Apply all formatting in a single batch (single API call)
        if format_requests:
            sheet.batch_format(format_requests)


    def _find_matching_pairs(self, data: List[List[str]]) -> Set[Tuple[int, int]]:
        """Find exact matching pairs between Column L and Column M values across all rows"""
        matched_pairs = set()
        
        # Build dictionaries for direct string matching
        col_l_values = {}  # {value: [row_indices]}
        col_m_values = {}  # {value: [row_indices]}
        
        # Collect all Column L and Column M values
        for i, row in enumerate(data[1:], 1):  # Skip header, start from row 1 (0-indexed)
            if len(row) > 12:  # Ensure we have both columns L and M
                # Column L (index 11) - direct string comparison
                col_l_raw = safe_str(row[11]) if len(row) > 11 and safe_str(row[11]) else None
                if col_l_raw:
                    if col_l_raw not in col_l_values:
                        col_l_values[col_l_raw] = []
                    col_l_values[col_l_raw].append(i)
                
                # Column M (index 12) - direct string comparison
                col_m_raw = safe_str(row[12]) if len(row) > 12 and safe_str(row[12]) else None
                if col_m_raw:
                    if col_m_raw not in col_m_values:
                        col_m_values[col_m_raw] = []
                    col_m_values[col_m_raw].append(i)
        
        # Find exact matches between Column L and Column M values
        for l_value, l_rows in col_l_values.items():
            if l_value in col_m_values:
                m_rows = col_m_values[l_value]
                
                # Match L rows with M rows (one-to-one pairing)
                used_m_rows = set()
                for l_row in l_rows:
                    for m_row in m_rows:
                        if l_row != m_row and m_row not in used_m_rows:  # Don't match row with itself or reuse M rows
                            matched_pairs.add((min(l_row, m_row), max(l_row, m_row)))
                            used_m_rows.add(m_row)
                            break  # Match each L row with only one M row
        
        logger.info(f"  � Matched {len(col_l_values)} unique Column L values with {len(col_m_values)} unique Column M values")
        
        return matched_pairs

    def _identify_unmatched_rows(self, data: List[List[str]], matched_pairs: Set[Tuple[int, int]]) -> List[int]:
        """Identify rows that are not part of any matched pair"""
        matched_row_indices = set()
        
        # Collect all row indices that are part of matched pairs
        for pair in matched_pairs:
            matched_row_indices.add(pair[0])
            matched_row_indices.add(pair[1])
        
        # Find unmatched rows (rows that have data in L or M but aren't matched)
        unmatched_rows = []
        
        for i, row in enumerate(data[1:], 1):  # Skip header, start from row 1 (0-indexed)
            if len(row) > 12:  # Ensure we have both columns L and M
                col_l_val = safe_str(row[11]) if len(row) > 11 and safe_str(row[11]) else None
                col_m_val = safe_str(row[12]) if len(row) > 12 and safe_str(row[12]) else None
                
                # If row has data in L or M but is not matched
                if (col_l_val or col_m_val) and i not in matched_row_indices:
                    unmatched_rows.append(i)
        
        return unmatched_rows

    def _clear_output_sheets(self) -> None:
        """Clear existing data AND formatting in 'Matched' and 'Unmatched' sheets"""
        logger.info("🧹 Clearing existing data and formatting in output sheets...")
        
        # Clear or create "Matched" sheet
        try:
            matched_sheet = self.workbook.worksheet("Matched")
            matched_sheet.clear()  # Clear content
            
            # Clear all formatting (including background colors)
            try:
                sheet_id = matched_sheet.id
                clear_format_request = {
                    "requests": [{
                        "updateCells": {
                            "range": {
                                "sheetId": sheet_id
                            },
                            "fields": "userEnteredFormat"
                        }
                    }]
                }
                self.workbook.batch_update(clear_format_request)
                logger.info("  ✅ Cleared 'Matched' sheet (content + formatting)")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not clear formatting from 'Matched' sheet: {e}")
                logger.info("  ✅ Cleared 'Matched' sheet (content only)")
        except gspread.WorksheetNotFound:
            matched_sheet = self.workbook.add_worksheet(title="Matched", rows=1000, cols=17)  # A-P + Q
            logger.info("  ✅ Created new 'Matched' sheet")
        
        # Clear or create "Unmatched" sheet
        try:
            unmatched_sheet = self.workbook.worksheet("Unmatched")
            unmatched_sheet.clear()  # Clear content
            
            # Clear all formatting (including background colors)
            try:
                sheet_id = unmatched_sheet.id
                clear_format_request = {
                    "requests": [{
                        "updateCells": {
                            "range": {
                                "sheetId": sheet_id
                            },
                            "fields": "userEnteredFormat"
                        }
                    }]
                }
                self.workbook.batch_update(clear_format_request)
                logger.info("  ✅ Cleared 'Unmatched' sheet (content + formatting)")
            except Exception as e:
                logger.warning(f"  ⚠️  Could not clear formatting from 'Unmatched' sheet: {e}")
                logger.info("  ✅ Cleared 'Unmatched' sheet (content only)")
        except gspread.WorksheetNotFound:
            unmatched_sheet = self.workbook.add_worksheet(title="Unmatched", rows=1000, cols=16)  # A-P
            logger.info("  ✅ Created new 'Unmatched' sheet")

    def _write_matched_pairs_to_sheet(self, source_data: List[List[str]], matched_pairs: Set[Tuple[int, int]], phase_label: str) -> None:
        """Write matched pairs to 'Matched' sheet with stacking and phase labeling"""
        if not matched_pairs:
            logger.info("  📋 No matched pairs to write")
            return
        
        # Get header row (extend to include Column Q for phase labeling)
        header_row = source_data[0][:16] if len(source_data[0]) >= 16 else source_data[0]  # Columns A-P
        header_row = header_row + ["Matching Logic"]  # Add Column Q header
        
        # Prepare matched data with stacking (lower row number first)
        matched_data = [header_row]
        
        for pair in sorted(matched_pairs):  # Sort pairs for consistent output
            row1_idx, row2_idx = pair
            
            # Get the two rows (columns A-P)
            row1 = source_data[row1_idx][:16] if len(source_data[row1_idx]) >= 16 else source_data[row1_idx]
            row2 = source_data[row2_idx][:16] if len(source_data[row2_idx]) >= 16 else source_data[row2_idx]
            
            # Stack by lower row number first, add phase label in Column Q
            matched_data.append(row1 + [phase_label])
            matched_data.append(row2 + [phase_label])
        
        # Process rows to format Column B dates
        matched_data = convert_column_b_to_serial(matched_data)
        
        # Write to "Matched" sheet
        try:
            matched_sheet = self.workbook.worksheet("Matched")
            matched_sheet.update(matched_data, value_input_option='RAW')
            
            # Batch format all columns in a single API call
            batch_format_columns(
                matched_sheet,
                date_ranges=['B2:B'],
                date_mmyyyy_ranges=['C2:C'],
                text_ranges=['E2:E'],
                number_ranges={'F2:F': '#,##0.00', 'G2:G': '#,##0.00'}
            )
            
            logger.info(f"  📋 Updated 'Matched' sheet with {len(matched_pairs)} pairs ({len(matched_pairs) * 2} transactions)")
        except Exception as e:
            logger.error(f"  ❌ Error updating 'Matched' sheet: {e}")

    def _write_unmatched_to_sheet(self, source_data: List[List[str]], unmatched_row_indices: List[int]) -> None:
        """Write unmatched transactions to 'Unmatched' sheet, sorted by Column O"""
        if not unmatched_row_indices:
            logger.info("  📋 No unmatched transactions to write")
            return
        
        # Get header row (columns A-P)
        header_row = source_data[0][:16] if len(source_data[0]) >= 16 else source_data[0]
        
        # Collect unmatched rows (columns A-P only)
        unmatched_rows = []
        for row_idx in sorted(unmatched_row_indices):
            if row_idx < len(source_data):
                row = source_data[row_idx][:16] if len(source_data[row_idx]) >= 16 else source_data[row_idx]
                unmatched_rows.append(row)
        
        # Sort by Column O (index 14) with proper handling of different data types
        logger.info("  🔄 Sorting unmatched transactions by Column O values...")
        def sort_key(row):
            if len(row) <= 14 or not row[14]:
                return "zzz_empty"  # Put empty values at the end
            
            col_o_val = safe_str(row[14])
            # Try to parse as number for proper numeric sorting
            try:
                return f"{float(col_o_val):010.2f}"  # Pad numbers for proper sorting
            except (ValueError, TypeError):
                return col_o_val  # Keep as string if not numeric
        
        sorted_unmatched_rows = sorted(unmatched_rows, key=sort_key)
        
        # Group and log Column O categories for analysis
        column_o_groups = {}
        for row in sorted_unmatched_rows:
            col_o_val = safe_str(row[14]) if len(row) > 14 and safe_str(row[14]) else "EMPTY"
            if col_o_val not in column_o_groups:
                column_o_groups[col_o_val] = 0
            column_o_groups[col_o_val] += 1
        
        logger.info(f"  📊 Organized {len(unmatched_row_indices)} transactions into {len(column_o_groups)} Column O categories:")
        for group_name, count in sorted(column_o_groups.items())[:10]:  # Show first 10 categories
            logger.info(f"    • {group_name}: {count} transactions")
        if len(column_o_groups) > 10:
            logger.info(f"    ... and {len(column_o_groups) - 10} more categories")
        
        # Prepare final data for unmatched sheet
        unmatched_data = [header_row] + sorted_unmatched_rows
        
        # Process rows to format Column B dates
        unmatched_data = convert_column_b_to_serial(unmatched_data)
        
        # Write to "Unmatched" sheet
        try:
            unmatched_sheet = self.workbook.worksheet("Unmatched")
            unmatched_sheet.update(unmatched_data, value_input_option='RAW')
            
            # Batch format all columns in a single API call
            batch_format_columns(
                unmatched_sheet,
                date_ranges=['B2:B'],
                date_mmyyyy_ranges=['C2:C'],
                text_ranges=['E2:E'],
                number_ranges={'F2:F': '#,##0.00', 'G2:G': '#,##0.00'}
            )
            
            logger.info(f"  📋 Updated 'Unmatched' sheet with {len(unmatched_row_indices)} transactions (sorted by Column O)")
        except Exception as e:
            logger.error(f"  ❌ Error updating 'Unmatched' sheet: {e}")

    def _append_balanced_to_matched(self, balanced_subsidiaries: List[Dict]) -> None:
        """Append balanced subsidiary transactions to 'Matched' sheet with Phase 2 labels"""
        logger.info("  📋 Appending balanced subsidiaries to 'Matched' sheet...")
        
        # Prepare balanced transactions with Phase 2 labels
        balanced_transactions = []
        
        for subsidiary in balanced_subsidiaries:
            for row in subsidiary['rows']:
                # Add Column Q = "Phase 2" to each transaction
                transaction_with_label = row + ["Phase 2"]
                balanced_transactions.append(transaction_with_label)
        
        if not balanced_transactions:
            logger.info("  📋 No balanced transactions to append")
            return
        
        # Process rows to format Column B dates
        balanced_transactions = convert_column_b_to_serial([["Header"]] + balanced_transactions)[1:]  # Skip fake header
        
        # Append to "Matched" sheet (simple append, no reading existing data)
        try:
            matched_sheet = self.workbook.worksheet("Matched")
            
            # Get current data count to know where to start appending (use UNFORMATTED_VALUE)
            existing_data = matched_sheet.get(value_render_option='UNFORMATTED_VALUE')
            next_row = len(existing_data) + 1
            
            # Append balanced transactions starting from next available row
            start_range = f"A{next_row}"
            end_col = chr(65 + len(balanced_transactions[0]) - 1)  # A-P + Q
            end_range = f"{end_col}{next_row + len(balanced_transactions) - 1}"
            
            matched_sheet.update(
                values=balanced_transactions,
                range_name=f"{start_range}:{end_range}",
                value_input_option='RAW'
            )
            
            # Batch format all columns in a single API call
            batch_format_columns(
                matched_sheet,
                date_ranges=[f'B{next_row}:B{next_row + len(balanced_transactions) - 1}'],
                date_mmyyyy_ranges=[f'C{next_row}:C{next_row + len(balanced_transactions) - 1}'],
                text_ranges=[f'E{next_row}:E{next_row + len(balanced_transactions) - 1}'],
                number_ranges={
                    f'F{next_row}:F{next_row + len(balanced_transactions) - 1}': '#,##0.00',
                    f'G{next_row}:G{next_row + len(balanced_transactions) - 1}': '#,##0.00'
                }
            )
            
            logger.info(f"  📋 Appended {len(balanced_transactions)} balanced transactions to 'Matched' sheet (rows {next_row}-{next_row + len(balanced_transactions) - 1})")
            
        except Exception as e:
            logger.error(f"  ❌ Error appending to 'Matched' sheet: {e}")

    def _update_unmatched_with_remaining(self, header_row: List[str], unbalanced_subsidiaries: List[Dict], original_count: int) -> None:
        """Update 'Unmatched' sheet with remaining unbalanced transactions"""
        
        # Collect all unbalanced transactions
        remaining_transactions = []
        for subsidiary in unbalanced_subsidiaries:
            remaining_transactions.extend(subsidiary['rows'])
        
        new_count = len(remaining_transactions)
        
        # Check if there's a difference using row count comparison
        if new_count < original_count:
            logger.info(f"  🔄 Updating 'Unmatched' sheet: {original_count} → {new_count} transactions ({original_count - new_count} removed)")
            
            # Sort remaining transactions by Column O for consistency
            def sort_key(row):
                if len(row) <= 14 or not row[14]:
                    return "zzz_empty"
                col_o_val = safe_str(row[14])
                try:
                    return f"{float(col_o_val):010.2f}"
                except (ValueError, TypeError):
                    return col_o_val
            
            sorted_remaining = sorted(remaining_transactions, key=sort_key)
            
            # Update "Unmatched" sheet with remaining transactions
            header_ap = header_row[:16] if len(header_row) >= 16 else header_row
            updated_data = [header_ap] + sorted_remaining
            
            # Process rows to format Column B dates
            updated_data = convert_column_b_to_serial(updated_data)
            
            try:
                unmatched_sheet = self.workbook.worksheet("Unmatched")
                unmatched_sheet.clear()
                unmatched_sheet.update(updated_data, value_input_option='RAW')
                
                # Batch format all columns in a single API call
                batch_format_columns(
                    unmatched_sheet,
                    date_ranges=['B2:B'],
                    date_mmyyyy_ranges=['C2:C'],
                    text_ranges=['E2:E'],
                    number_ranges={'F2:F': '#,##0.00', 'G2:G': '#,##0.00'}
                )
                
                logger.info(f"  📋 Updated 'Unmatched' sheet with {new_count} remaining transactions")
                
            except Exception as e:
                logger.error(f"  ❌ Error updating 'Unmatched' sheet: {e}")
        else:
            logger.info(f"  📋 No change in transaction count ({original_count}) - 'Unmatched' sheet unchanged")


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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Complete transaction reconciliation pipeline (Phase 1-5)")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="Target Google Sheet ID")
    parser.add_argument("--service-account", default=None, help="Override path to Google service account JSON file")
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")

    parser.add_argument("--phase1-only", action="store_true", help="Run Phase 1 only (disable Phase 2, 3, 4, and 5)")
    parser.add_argument("--no-phase2", action="store_true", help="Skip Phase 2: Subsidiary balance elimination")
    parser.add_argument("--no-phase3", action="store_true", help="Skip Phase 3: Intercompany transaction matching")
    parser.add_argument("--phase4", action="store_true", help="Enable Phase 4: Manual reconciliation with suggestive matching")
    parser.add_argument("--phase4-only", action="store_true", help="Run Phase 4 only (skip Phases 1-3, assumes data already in sheets)")
    parser.add_argument("--phase5-only", action="store_true", help="Run Phase 5 only (generate subsidiary ledger T-accounts and SL Summary)")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s | %(message)s")

    # Resolve StorSafe project root (this file lives under: <storsafe_root>/1. Account Reconciliation/)
    try:
        project_root = Path(__file__).resolve().parents[1]
    except NameError:
        project_root = Path.cwd()

    service_account_path = _resolve_service_account_path(project_root, args.service_account)

    # Determine which phases to run
    if args.phase5_only:
        # Skip Phases 1-4, only run Phase 5
        run_phase1 = False
        run_phase2 = False
        run_phase3 = False
        run_phase4 = False
    elif args.phase4_only:
        # Skip Phases 1-3, only run Phase 4
        run_phase1 = False
        run_phase2 = False
        run_phase3 = False
        run_phase4 = True
    else:
        # Default: Phase 1-4 run automatically (Phase 4 auto-enabled)
        run_phase1 = True
        run_phase2 = not (args.phase1_only or args.no_phase2)
        run_phase3 = not (args.phase1_only or args.no_phase3)
        run_phase4 = not args.phase1_only  # Auto-enable Phase 4 unless phase1-only is specified

    reconciler = TransactionReconciler(
        sheet_id=args.sheet_id,
        service_account_path=service_account_path,
        run_phase2=run_phase2,
        run_phase3=run_phase3,
        run_phase4=run_phase4
    )

    # Handle different run modes
    if args.phase5_only:
        # Directly run Phase 5 without going through reconcile_transactions()
        logger.info("Starting transaction reconciliation...")
        logger.info("=" * 60)
        logger.info("🔄 PHASE 5 ONLY MODE")
        logger.info("=" * 60)
        reconciler._run_phase5()
    elif args.phase4_only:
        # Directly run Phase 4 without going through reconcile_transactions()
        logger.info("Starting transaction reconciliation...")
        logger.info("=" * 60)
        logger.info("🔄 PHASE 4 ONLY MODE")
        logger.info("=" * 60)
        reconciler._run_phase4()
    else:
        reconciler.reconcile_transactions()
    
    logger.info("✅ Transaction reconciliation completed!")


if __name__ == "__main__":
    main()
