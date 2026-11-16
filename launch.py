#!/usr/bin/env python3
"""Run directly from a checkout without installing dependencies."""

import os
import sys
from pathlib import Path

runtime = Path(__file__).resolve().parent / ".venv-agent"
if (runtime / "bin/python").exists() and Path(sys.prefix).resolve() != runtime.resolve():
    os.execv(
        str(runtime / "bin/python"),
        [str(runtime / "bin/python"), str(Path(__file__).resolve()), *sys.argv[1:]],
    )

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from fitness_tracker.server import main  # noqa: E402

if __name__ == "__main__":
    main()
