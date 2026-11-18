#!/usr/bin/env python3
"""
Single-command runner for WBFM dual pipeline.
Usage:
  wbsegmentation [optional_raw_folder]
  wbsegmentation status <project_folder>
  wbsegmentation verify <project_folder>
"""
import sys
from pathlib import Path

automation_dir = Path(__file__).resolve().parent / "automation"
sys.path.insert(0, str(automation_dir))

from auto_pipeline import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append("go")
    elif sys.argv[1] not in ["go", "sanitize", "status", "verify", "check-ids", "-h", "--help"]:
        sys.argv.insert(1, "go")
    main()
