#!/usr/bin/env python3
"""Create a Finder/Spotlight launcher pointing at this checkout."""

import plistlib
import shlex
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
app = Path.home() / "Applications" / "Blaze Athletics.app"
for name in ("blaze.app", "Form & Fuel.app"):
    previous = app.with_name(name)
    if previous.exists() and not app.exists():
        previous.rename(app)
contents = app / "Contents"
(contents / "MacOS").mkdir(parents=True, exist_ok=True)
(contents / "Resources").mkdir(exist_ok=True)
info = {
    "CFBundleName": "Blaze Athletics",
    "CFBundleDisplayName": "Blaze Athletics",
    "CFBundleIdentifier": "local.formandfuel.fitness",
    "CFBundleExecutable": "Blaze",
    "CFBundleIconFile": "blaze.icns",
    "CFBundleVersion": "1.0",
    "CFBundlePackageType": "APPL",
    "NSHighResolutionCapable": True,
}
with (contents / "Info.plist").open("wb") as f:
    plistlib.dump(info, f)
shutil.copy2(root / "src/fitness_tracker/web/assets/blaze.icns", contents / "Resources/blaze.icns")
launcher = contents / "MacOS" / "Blaze"
launcher.write_text(
    "#!/bin/zsh\ncd "
    + shlex.quote(str(root))
    + "\nmkdir -p data\nexec /usr/bin/python3 scripts/start.py >> data/server.log 2>&1\n"
)
launcher.chmod(0o755)
print("Installed:", app)
print("This launcher opens the local browser app. Keep the checkout at:", root)
