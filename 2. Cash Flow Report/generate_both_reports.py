"""
Generate Both Monthly and YTD Cash Flow Reports

Wrapper script that generates both monthly and YTD reports in a single run.
Modifies the main script configuration and executes it twice.
"""

import subprocess
import sys
import time
from pathlib import Path

# Configuration
MONTH = "Sep"
YEAR = 2025
SCRIPT_PATH = Path(__file__).parent / "generate_cashflow_report.py"
SLEEP_BETWEEN_REPORTS = 90  # Seconds to wait between monthly and YTD (avoid API issues)

print("=" * 80)
print("CASH FLOW REPORT GENERATION - MONTHLY + YTD")
print("=" * 80)
print(f"\nGenerating both Monthly and YTD reports for {MONTH} {YEAR}")
print(f"Script: {SCRIPT_PATH}\n")

# Report types to generate
REPORT_TYPES = ["monthly", "ytd"]

for idx, report_type in enumerate(REPORT_TYPES):
    # Add delay between reports to avoid API rate limits
    if idx > 0:
        print(f"\n\n⏱ Waiting {SLEEP_BETWEEN_REPORTS} seconds between reports to avoid API rate limits...")
        time.sleep(SLEEP_BETWEEN_REPORTS)
    
    print("\n" + "=" * 80)
    print(f"GENERATING {report_type.upper()} REPORT ({idx+1}/2)")
    print("=" * 80 + "\n")
    
    # Read the script
    with open(SCRIPT_PATH, 'r', encoding='utf-8') as f:
        script_content = f.read()
    
    # Modify REPORT_TYPE configuration
    # Find the line with REPORT_TYPE = and replace it
    lines = script_content.split('\n')
    modified_lines = []
    
    for line in lines:
        if line.strip().startswith('REPORT_TYPE ='):
            # Replace with current report type
            modified_lines.append(f'REPORT_TYPE = "{report_type}"     # "monthly" or "ytd"')
        else:
            modified_lines.append(line)
    
    modified_content = '\n'.join(modified_lines)
    
    # Write temporary script
    temp_script = SCRIPT_PATH.parent / f"_temp_generate_{report_type}.py"
    with open(temp_script, 'w', encoding='utf-8') as f:
        f.write(modified_content)
    
    # Execute the modified script
    try:
        result = subprocess.run(
            [sys.executable, str(temp_script)],
            capture_output=False,
            text=True,
            check=True
        )
        
        print(f"\n✅ {report_type.upper()} report generated successfully")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error generating {report_type} report")
        print(f"Exit code: {e.returncode}")
        
        # Clean up temp file
        if temp_script.exists():
            temp_script.unlink()
        
        sys.exit(1)
    
    finally:
        # Clean up temp file
        if temp_script.exists():
            temp_script.unlink()

print("\n\n" + "=" * 80)
print("✅ BOTH REPORTS GENERATED SUCCESSFULLY")
print("=" * 80)
print(f"\nGenerated:")
print(f"  📊 Monthly: Cash Flow Report (All) - {MONTH}")
print(f"  📊 YTD: Cash Flow Report (All) - YTD.{MONTH}")
print(f"\nReady to populate Summary Page with populate_summary_page.py")
