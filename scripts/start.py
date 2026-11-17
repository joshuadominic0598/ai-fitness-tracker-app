#!/usr/bin/env python3
"""Set up this checkout on first run, then open the local app."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Prepare and start Blaze Athletics", add_help=False
    )
    parser.add_argument("--no-open", action="store_true", help="Keep the browser closed")
    options, app_args = parser.parse_known_args()
    if sys.version_info < (3, 10):
        os.environ["PATH"] = os.pathsep.join(
            [os.environ.get("PATH", ""), "/opt/homebrew/bin", "/usr/local/bin"]
        )
        newer = next(
            (
                shutil.which(name)
                for name in ("python3.14", "python3.13", "python3.12", "python3.11", "python3.10")
                if shutil.which(name)
            ),
            None,
        )
        if not newer:
            raise SystemExit(
                "Please install Python 3.10 or newer from python.org, then open Start Blaze Athletics again."
            )
        os.execv(newer, [newer, str(Path(__file__).resolve()), *sys.argv[1:]])
    runtime = root / ".venv-agent"
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        print("Preparing Blaze Athletics for your computer…", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(runtime)], check=True)
    ready = subprocess.run(
        [str(python), "-c", "import langgraph, tiktoken, ddgs, faster_whisper"], capture_output=True
    )
    if ready.returncode:
        print("Installing the app's first-run requirements. This needs internet once.", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "-e", str(root)], check=True)
    print("Opening Blaze Athletics. Start Ollama to use your Qwen coach.", flush=True)
    return subprocess.call(
        [str(python), str(root / "launch.py"), *([] if options.no_open else ["--open"]), *app_args],
        cwd=root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
