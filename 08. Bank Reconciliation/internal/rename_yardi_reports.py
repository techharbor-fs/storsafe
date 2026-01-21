#!/usr/bin/env python3
"""
Yardi Report Renaming Utility

Analyzes Bank_Rec Excel files and renames them to standardized format:
    {Year}-{Month}_Bank_Rec_{Property}.xlsx

Usage:
    # Dry run (show what would be renamed without changing files)
    python rename_yardi_reports.py "12. Dec"
    
    # Actually rename files
    python rename_yardi_reports.py "12. Dec" --rename
    
    # Process all monthly folders
    python rename_yardi_reports.py . --rename
"""

import argparse
import sys
from pathlib import Path

# Add internal to path for imports
sys.path.insert(0, str(Path(__file__).parent / "internal"))

from internal.parsers import analyze_yardi_report, rename_yardi_report


def find_yardi_files(folder: Path) -> list[Path]:
    """Find all Bank_Rec Excel files in folder and subfolders."""
    files = []
    
    # Look for Bank_Rec*.xlsx files
    for pattern in ["Bank_Rec*.xlsx", "Bank_Rec*.xls", "*Bank_Rec*.xlsx"]:
        files.extend(folder.glob(pattern))
        files.extend(folder.glob(f"**/{pattern}"))
    
    # Also look for files that might already be renamed (YYYY-MM_Bank_Rec_*.xlsx)
    files.extend(folder.glob("**/[0-9][0-9][0-9][0-9]-[0-9][0-9]_Bank_Rec_*.xlsx"))
    
    # De-duplicate and sort
    unique_files = list(set(files))
    unique_files.sort()
    
    return unique_files


def main():
    parser = argparse.ArgumentParser(
        description="Analyze and rename Yardi Bank_Rec Excel files to standardized format."
    )
    parser.add_argument(
        "folder",
        type=str,
        help="Folder to search for Bank_Rec files (can include subfolders)"
    )
    parser.add_argument(
        "--rename",
        action="store_true",
        help="Actually rename files (without this flag, only shows what would change)"
    )
    args = parser.parse_args()
    
    folder = Path(args.folder)
    if not folder.exists():
        print(f"Error: Folder not found: {folder}")
        sys.exit(1)
    
    dry_run = not args.rename
    
    print("=" * 70)
    print("Yardi Report Renaming Utility")
    print("=" * 70)
    print()
    print(f"Searching: {folder.absolute()}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'RENAME (files will be changed)'}")
    print()
    
    files = find_yardi_files(folder)
    
    if not files:
        print("No Bank_Rec Excel files found.")
        return
    
    print(f"Found {len(files)} file(s) to analyze:")
    print()
    
    results = {
        "would_rename": [],
        "already_correct": [],
        "failed": [],
    }
    
    for file_path in files:
        # Analyze the file
        analysis = analyze_yardi_report(file_path)
        
        print(f"  File: {file_path.relative_to(folder) if file_path.is_relative_to(folder) else file_path}")
        print(f"    Property: {analysis['property'] or '(not detected)'}")
        print(f"    Period: {analysis['month'] or '?'}/{analysis['year'] or '?'}")
        print(f"    Confidence: {analysis['confidence']}")
        
        if not analysis["suggested_name"]:
            print(f"    Status: CANNOT RENAME - missing required info")
            results["failed"].append((file_path, "Missing property/period"))
        elif file_path.name == analysis["suggested_name"]:
            print(f"    Status: Already correct")
            results["already_correct"].append(file_path)
        else:
            print(f"    Suggested: {analysis['suggested_name']}")
            
            if not dry_run:
                success, message, new_path = rename_yardi_report(file_path)
                if success:
                    print(f"    Status: RENAMED")
                    results["would_rename"].append((file_path, new_path))
                else:
                    print(f"    Status: FAILED - {message}")
                    results["failed"].append((file_path, message))
            else:
                print(f"    Status: Would rename (dry run)")
                results["would_rename"].append((file_path, analysis["suggested_name"]))
        
        print()
    
    # Summary
    print("=" * 70)
    print("Summary:")
    print(f"  Would rename:    {len(results['would_rename'])}")
    print(f"  Already correct: {len(results['already_correct'])}")
    print(f"  Failed:          {len(results['failed'])}")
    
    if dry_run and results["would_rename"]:
        print()
        print("To actually rename files, run with --rename flag:")
        print(f"  python rename_yardi_reports.py \"{folder}\" --rename")


if __name__ == "__main__":
    main()
