#!/usr/bin/env python3
"""Rebuild the pinned public-domain catalog and local thumbnails (requires Pillow)."""

import concurrent.futures
import io
import json
import pathlib
import urllib.request

from PIL import Image

root = pathlib.Path(__file__).resolve().parents[1]
base = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/f00c92c7dcf1216a928a52c3706c7ce8e2f71ed5/"


def get(path):
    return urllib.request.urlopen(base + path, timeout=40).read()


raw = get("dist/exercises.json")
data = [e for e in json.loads(raw) if e.get("images")]
(root / "src/fitness_tracker/exercises.json").write_text(json.dumps(data, separators=(",", ":")))
(root / "docs/EXERCISE_DATA_LICENSE").write_bytes(get("LICENSE.md"))


def thumbnail(e):
    target = root / "src/fitness_tracker/web/assets/exercises" / (e["id"] + ".webp")
    if target.exists():
        return True
    for attempt in range(3):
        try:
            im = Image.open(io.BytesIO(get("exercises/" + e["images"][0]))).convert("RGB")
            im.thumbnail((280, 210))
            im.save(target, "WEBP", quality=72)
            return True
        except Exception:
            pass
    return e["id"]


with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    results = list(pool.map(thumbnail, data))
print(
    "Exercises:",
    len(data),
    "Images:",
    sum(x is True for x in results),
    "Failed:",
    [x for x in results if x is not True],
)
