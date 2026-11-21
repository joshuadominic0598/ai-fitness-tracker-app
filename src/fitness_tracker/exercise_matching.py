"""Per-movement library retrieval, independent of journal history and model IDs."""

import re
from difflib import SequenceMatcher
from functools import lru_cache


@lru_cache(maxsize=8192)
def normalize(value):
    value = str(value).casefold().replace("_", " ").replace("-", " ")
    for pattern, replacement in (
        (r"\b(?:single|one)\s+arm\b", "unilateral"),
        (r"\b(?:both|two)\s+arms?\b", ""),
        (r"\b(?:push\s*ups?|pushups)\b", "pushup"),
        (r"\b(?:sit\s*ups?|situps)\b", "situp"),
        (r"\b(?:pull\s*ups?|pullups)\b", "pullup"),
        (r"\bcunches\b", "crunches"),
        (r"\bwide grip lat\b|\blat wide grip\b", "wide grip lat"),
        (r"\blegpress\b", "leg press"),
        (r"\bpush\s*downs?\b", "pushdown"),
        (r"\bpull\s*downs?\b", "pulldown"),
        (r"\b(?:flyes|flies)\b", "fly"),
        (r"\btriceps?\b", "tricep"),
        (r"\bbiceps?\b", "bicep"),
        (r"\bdumbells?\b", "dumbbell"),
        (r"\b(curl|raise|row|squat|extension|press|thrust)s\b", r"\1"),
    ):
        value = re.sub(pattern, replacement, value)
    return " ".join(re.findall(r"[a-z]+", value))


def rank_exercises(value, limit=4, retriever=None):
    """Return suitable real IDs; unrelated movements never become a fallback."""
    from .store import CATALOG

    query = normalize(value)
    if "row" in query.split() and "cable" in query.split():
        query = query.replace("close grip", "").strip()
    stop = set(
        "then and did like warm up set sets rep reps kg either side total weight loaded machine exercise cable arm".split()
    )
    words = set(query.split()) - stop
    if not words:
        return []
    ranked = []
    for exercise in CATALOG:
        names = [exercise["name"], *exercise.get("aliases", [])]
        score = 0
        for name in names:
            normalized = normalize(name)
            tokens = set(normalized.split()) - stop
            movement_words = {
                "press",
                "curl",
                "row",
                "squat",
                "deadlift",
                "fly",
                "raise",
                "thrust",
                "plank",
                "pushdown",
                "pulldown",
                "pushup",
                "pullup",
                "extension",
            }
            required = words & movement_words
            if required and not required <= tokens:
                continue
            anatomy_words = {"shoulder", "chest", "tricep", "bicep", "calf", "leg", "lat"}
            if words & anatomy_words and not (words & anatomy_words) <= tokens:
                continue
            overlap = sum(
                max((SequenceMatcher(None, word, token).ratio() for token in tokens), default=0)
                >= 0.82
                for word in words
            )
            coverage = overlap / len(words)
            if coverage < 0.65:
                continue
            candidate_score = coverage * 10 + overlap - len(tokens - words) * 0.6
            if normalized == query or re.search(r"\b" + re.escape(normalized) + r"\b", query):
                candidate_score += 8
            for qualifier in (
                "dumbbell",
                "barbell",
                "rope",
                "unilateral",
                "incline",
                "decline",
                "rear",
                "reverse",
                "low",
                "seated",
                "standing",
                "smith",
            ):
                if (qualifier in query.split()) != (qualifier in normalized.split()):
                    candidate_score -= 3
            for equipment in ("cable", "machine", "dumbbell", "barbell"):
                if (
                    equipment in query.split()
                    and equipment not in normalized.split()
                    and equipment != exercise.get("equipment")
                ):
                    candidate_score -= 5
            score = max(score, candidate_score)
        if score >= 7:
            ranked.append((score, exercise["id"]))
    ranked.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
    identifiers = [identifier for _, identifier in ranked[:limit]]
    if retriever:
        semantic = retriever.search(value, category="exercise", limit=max(24, limit * 8))
        for result in semantic:
            identifier = result["id"].removeprefix("exercise:")
            exercise = next((ex for ex in CATALOG if ex["id"] == identifier), None)
            if not exercise:
                continue
            terms = set(
                normalize(exercise["name"] + " " + " ".join(exercise.get("aliases", []))).split()
            )
            required = words & {
                "press",
                "curl",
                "row",
                "squat",
                "deadlift",
                "fly",
                "raise",
                "thrust",
                "plank",
                "pushdown",
                "pulldown",
                "pushup",
                "pullup",
                "extension",
                "shoulder",
                "chest",
                "tricep",
                "bicep",
                "calf",
                "leg",
                "lat",
            }
            if required and not required <= terms:
                continue
            if (
                result["retrieval"].startswith("semantic")
                and result["score"] >= 0.35
                and identifier not in identifiers
            ):
                identifiers.append(identifier)
        # An unspecified posture must not turn a leg raise into a shoulder press.
        # Relax posture/equipment only for a confirmation shortlist, never an automatic match.
        if not identifiers:
            relaxed = " ".join(
                word
                for word in query.split()
                if word not in {"standing", "seated", "machine", "cable"}
            )
            if relaxed and relaxed != query:
                identifiers = rank_exercises(relaxed, limit=limit)
    return identifiers[:limit]


def canonical_id(identifier, candidates):
    """Accept human-readable spellings only within this movement's shortlist."""
    key = normalize(str(identifier))
    return next((eid for eid in candidates if normalize(eid) == key), None)
