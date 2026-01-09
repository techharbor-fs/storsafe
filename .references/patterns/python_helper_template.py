"""One-shot helper script template (copy into a project before using).

Purpose
- Provides a safe, bounded helper/inspector scaffold.
- Enforces:
  - `--timeout-seconds` (default 60)
  - Start banner + end banner
  - Structured JSON summary artifact
  - Explicit completion marker: `FINAL_MARKER: ...`

How to use
1) Copy this file into the appropriate project-level `.helper_artifacts/<bucket>/` folder.
2) Rename it (e.g., `inspect_<topic>.py`).
3) Implement `do_work(ctx)` and call `ctx.check_timeout()` periodically inside loops.

Notes
- This template cannot forcibly stop arbitrary Python work on timeout. Instead:
  - it provides a deadline and a `check_timeout()` helper;
  - your implementation should call it at safe checkpoints.
- For subprocess calls, always pass timeouts (see `run_subprocess`).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class RunContext:
    started_at_iso: str
    timeout_seconds: float
    deadline_monotonic: float
    output_dir: Path
    summary_json_path: Path
    preview_txt_path: Path | None

    def check_timeout(self) -> None:
        if time.monotonic() >= self.deadline_monotonic:
            raise TimeoutError(f"Timed out after {self.timeout_seconds} seconds")


def run_subprocess(
    args: list[str],
    *,
    timeout_seconds: float,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="Hard time budget for the helper (default: 60).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="artifacts",
        help="Output folder (relative to this script). Default: artifacts/",
    )
    return parser.parse_args(argv)


def build_context(args: argparse.Namespace) -> RunContext:
    script_dir = Path(__file__).resolve().parent
    output_dir = (script_dir / args.output_dir).resolve()
    safe_mkdir(output_dir)

    started_at_iso = utc_now_iso()
    timeout_seconds = float(args.timeout_seconds)
    deadline_monotonic = time.monotonic() + max(timeout_seconds, 0.0)

    summary_json_path = output_dir / "summary.json"
    preview_txt_path = output_dir / "preview.txt"

    return RunContext(
        started_at_iso=started_at_iso,
        timeout_seconds=timeout_seconds,
        deadline_monotonic=deadline_monotonic,
        output_dir=output_dir,
        summary_json_path=summary_json_path,
        preview_txt_path=preview_txt_path,
    )


def print_run_start(*, script_name: str, started_at: str, argv: list[str]) -> None:
    print("=== RUN START ===")
    print(f"script: {script_name}")
    print(f"started_at: {started_at}")
    print(f"argv: {argv}")


def print_run_end(
    *,
    status: str,
    exit_code: int,
    elapsed_seconds: float,
    summary_json: Path,
    preview_txt: Path | None,
    other: list[Path] | None = None,
    key_counts: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> None:
    print("=== RUN END ===")
    print(f"status: {status}")
    print(f"exit_code: {exit_code}")
    print(f"elapsed_seconds: {elapsed_seconds:.3f}")
    print("artifacts:")
    print(f"  summary_json: {summary_json}")
    print(f"  preview_txt: {preview_txt if preview_txt else 'null'}")
    print(f"  other: {[str(p) for p in (other or [])]}")
    print(f"key_counts: {key_counts or {}}")
    print(f"warnings: {warnings or []}")
    print(f"FINAL_MARKER: {status}")


def write_summary_json(
    *,
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def do_work(ctx: RunContext) -> dict[str, Any]:
    """Implement your helper logic here.

    Requirements:
    - Call `ctx.check_timeout()` periodically in loops.
    - Return a dict of results to embed in the summary JSON.

    Raise exceptions normally; the wrapper will catch and record them.
    """
    ctx.check_timeout()
    raise NotImplementedError(
        "Template script: implement do_work(ctx) after copying this file into your helper folder."
    )


def main(argv: list[str]) -> int:
    started_monotonic = time.monotonic()
    args = parse_args(argv)
    ctx = build_context(args)

    script_name = Path(__file__).name
    print_run_start(script_name=script_name, started_at=ctx.started_at_iso, argv=argv)

    status = "FAILED"
    exit_code = 1
    warnings: list[str] = []
    key_counts: dict[str, Any] = {}
    other_artifacts: list[Path] = []
    error: dict[str, Any] | None = None
    results: dict[str, Any] = {}

    try:
        ctx.check_timeout()
        results = do_work(ctx) or {}
        ctx.check_timeout()
        status = "COMPLETED"
        exit_code = 0
    except TimeoutError as exc:
        status = "TIMEOUT"
        exit_code = 2
        error = {"type": type(exc).__name__, "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        status = "FAILED"
        exit_code = 1
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }

    finished_at_iso = utc_now_iso()
    elapsed_seconds = time.monotonic() - started_monotonic

    summary_payload: dict[str, Any] = {
        "status": status,
        "exit_code": exit_code,
        "started_at": ctx.started_at_iso,
        "finished_at": finished_at_iso,
        "elapsed_seconds": elapsed_seconds,
        "args": {
            "timeout_seconds": ctx.timeout_seconds,
            "output_dir": str(ctx.output_dir),
        },
        "artifacts": {
            "summary_json": str(ctx.summary_json_path),
            "preview_txt": str(ctx.preview_txt_path) if ctx.preview_txt_path else None,
            "other": [str(p) for p in other_artifacts],
        },
        "key_counts": key_counts,
        "warnings": warnings,
        "results": results,
        "error": error,
    }

    write_summary_json(path=ctx.summary_json_path, payload=summary_payload)

    print_run_end(
        status=status,
        exit_code=exit_code,
        elapsed_seconds=elapsed_seconds,
        summary_json=ctx.summary_json_path,
        preview_txt=ctx.preview_txt_path,
        other=other_artifacts,
        key_counts=key_counts,
        warnings=warnings,
    )

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
