#!/usr/bin/env python3
"""
Single-command 'go' runner for WBFM dual pipeline.
Usage:
  python go.py [optional_raw_folder]
  python go.py status <project_folder>
  python go.py verify <project_folder>
  python go.py check-ids <project_or_batch_folder> [--only-pending]
"""
import sys
from pathlib import Path

automation_dir = Path(__file__).resolve().parent / "automation"
sys.path.insert(0, str(automation_dir))

from auto_pipeline import main

if __name__ == "__main__":
    # If called with no arguments or directly with a folder path, default to 'go'
    if len(sys.argv) == 1:
        sys.argv.append("go")
    elif sys.argv[1] not in ["go", "sanitize", "status", "verify", "check-ids", "-h", "--help"]:
        sys.argv.insert(1, "go")
    main()
