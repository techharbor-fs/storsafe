"""Run the full monthly Property Cash Flow workflow (single obvious entrypoint).

This file exists purely to be the first thing you see in the folder.
It delegates to the real workflow runner.

Usage:
  python RUN_ME.py --month-folder "11. Nov" --target-sheet "<url>" --confirm --assume-yes

If you run it with no arguments:
- it opens a folder picker for the month folder
- it uses the last saved target sheet (and only prompts if missing)
- it runs the workflow for real (equivalent to passing --confirm)

Notes:
- This process deletes all other non-required tabs as part of the workflow.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _load_last_defaults(project_root: Path) -> tuple[str | None, str | None]:
    state_path = project_root / "data" / "output" / "cashflow_prep_state.json"
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None, None
        last_month = str(raw.get("last_month_folder") or "").strip() or None
        last_sheet = str(raw.get("last_target_sheet_id") or "").strip() or None
        return last_month, last_sheet
    except Exception:
        return None, None


def _list_month_folders(base_dir: Path) -> list[str]:
    # Month folders live next to this script: "10. Oct", "11. Nov", etc.
    out: list[str] = []
    try:
        for p in base_dir.iterdir():
            if not p.is_dir():
                continue
            name = p.name
            if name.lower() in {"internal", "__pycache__"}:
                continue
            # Keep it simple: anything that looks like "11. Xxx"
            if "." in name and name.split(".", 1)[0].strip().isdigit():
                out.append(name)
    except Exception:
        return []
    out.sort()
    return out


def _pick_month_folder_gui(base_dir: Path) -> tuple[str | None, bool, bool]:
    """Open a folder picker and return (folder_name, canceled, gui_available).

    - folder_name: "11. Nov" if selection is a direct child of base_dir.
    - canceled: True if user canceled the dialog.
    - gui_available: False if tkinter/filedialog isn't available.
    """

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return None, False, False

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            title="Select month folder (e.g. '11. Nov')",
            initialdir=str(base_dir),
            mustexist=True,
        )
        root.destroy()
    except Exception:
        return None, False, True

    selected = str(selected or "").strip()
    if not selected:
        return None, True, True

    try:
        selected_path = Path(selected).resolve()
        base_resolved = base_dir.resolve()
    except Exception:
        return None, False, True

    if not selected_path.is_dir():
        return None, False, True

    # Require selection to be directly under base_dir (prevents picking arbitrary folders).
    if selected_path.parent != base_resolved:
        return None, False, True

    return selected_path.name, False, True


def _prompt_choice(options: list[str], *, default_value: str | None) -> str:
    if not options:
        entered = input(
            f"Month folder (e.g. '11. Nov'){f' [default: {default_value}]' if default_value else ''}: "
        ).strip()
        return entered or (default_value or "")

    print("\nSelect month folder:")
    for i, opt in enumerate(options, start=1):
        print(f"  {i}. {opt}")

    default_idx = 1
    if default_value and default_value in options:
        default_idx = options.index(default_value) + 1
    choice = input(f"Enter number [1-{len(options)}] (default {default_idx}): ").strip()
    try:
        idx = int(choice)
    except Exception:
        idx = default_idx
    idx = max(1, min(len(options), idx))
    return options[idx - 1]


def _prompt_yes_no(prompt: str, *, default_no: bool = True) -> bool:
    suffix = "[y/N]" if default_no else "[Y/n]"
    entered = input(f"{prompt} {suffix}: ").strip().lower()
    if not entered:
        return not default_no
    return entered in {"y", "yes"}


def main() -> None:
    here = Path(__file__).resolve().parent
    project_root = here.parent
    workflow = here / "internal" / "run_monthly_cashflow_workflow.py"

    argv = sys.argv[1:]
    if not argv:
        try:
            last_month, last_sheet = _load_last_defaults(project_root)

            # Prefer a folder picker (Windows-friendly).
            picked_folder, canceled, gui_available = _pick_month_folder_gui(here)
            if canceled:
                print("\nCancelled month folder selection. Exiting.")
                raise SystemExit(0)

            month_folder = (picked_folder or "").strip()
            if not month_folder:
                # If GUI isn't available or selection was invalid, fall back to numbered prompt.
                options = _list_month_folders(here)
                month_folder = _prompt_choice(options, default_value=last_month).strip()

            if not month_folder:
                print("\nNo month folder provided; exiting.")
                raise SystemExit(2)

            # Minimal prompting: default to last-used target sheet; prompt only if missing.
            target_sheet = (last_sheet or "").strip()
            if not target_sheet:
                target_sheet = input("Target sheet link/ID: ").strip()
            if not target_sheet:
                print("\nNo target sheet provided; exiting.")
                raise SystemExit(2)

            print("\nRunning workflow (CONFIRMED).")
            print("- This will delete all other non-required tabs")

            argv = [
                "--month-folder",
                month_folder,
                "--target-sheet",
                target_sheet,
                "--confirm",
                "--assume-yes",
                # Default to building the v1 statement tabs as part of the unified workflow.
                # Use RUN_ME.py --skip-v1 to disable.
            ]
        except KeyboardInterrupt:
            print("\nCancelled. Exiting.")
            raise SystemExit(0)

    cmd = [sys.executable, str(workflow), *argv]
    raise SystemExit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
