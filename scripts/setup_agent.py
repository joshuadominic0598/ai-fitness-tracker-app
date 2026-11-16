#!/usr/bin/env python3
"""Prepare the local Python 3.10+ environment used by the Mac launcher."""

import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
python = (
    sys.executable
    if sys.version_info >= (3, 10)
    else next(
        (
            shutil.which(name)
            for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10")
            if shutil.which(name)
        ),
        None,
    )
)
if not python:
    raise SystemExit("Install Python 3.10 or newer, then run this setup again.")
runtime = root / ".venv-agent"
subprocess.run([python, "-m", "venv", str(runtime)], check=True)
subprocess.run([str(runtime / "bin/python"), "-m", "pip", "install", "-e", str(root)], check=True)
print("Agent runtime is ready. Run python3 launch.py --open.")
