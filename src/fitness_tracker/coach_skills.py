"""Select small, source-linked coaching modules instead of loading all training knowledge."""

import json
from pathlib import Path

ROOT = Path(__file__).parent / "coach_skills"
MANIFEST = json.loads((ROOT / "manifest.json").read_text())


def select_skills(message, focus=""):
    query = (message + " " + focus).casefold()
    ranked = sorted(
        MANIFEST[1:], key=lambda item: sum(word in query for word in item["keywords"]), reverse=True
    )
    selected = [MANIFEST[0]] + [
        item for item in ranked if any(word in query for word in item["keywords"])
    ][:3]
    if len(selected) == 1:
        selected.append(next(item for item in MANIFEST if item["id"] == "full_body"))
    return [{**item, "content": (ROOT / (item["id"] + ".md")).read_text()} for item in selected]


def skill_catalog():
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "sources": item["sources"],
            "content": (ROOT / (item["id"] + ".md")).read_text(),
        }
        for item in MANIFEST
    ]
