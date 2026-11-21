"""Local, persisted hybrid retrieval. Journal changes and chunks share a transaction."""

import hashlib
import json
import math
import re
import threading
import time
from datetime import date, timedelta

from .cardio import ACTIVITY_PATTERN

EMBED_MODEL = "embeddinggemma:latest"


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS coach_chunks (
        id TEXT PRIMARY KEY, category TEXT NOT NULL, day TEXT NOT NULL,
        content TEXT NOT NULL, digest TEXT NOT NULL, vector TEXT, model TEXT)""")


def upsert(con, identifier, category, day, content):
    digest = hashlib.sha256(content.encode()).hexdigest()
    con.execute(
        """INSERT INTO coach_chunks(id,category,day,content,digest) VALUES (?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET category=excluded.category,day=excluded.day,
        content=excluded.content,digest=excluded.digest,
        vector=CASE WHEN digest=excluded.digest THEN vector ELSE NULL END,
        model=CASE WHEN digest=excluded.digest THEN model ELSE NULL END""",
        (identifier, category, day, content, digest),
    )


def journal_chunk(con, identifier, kind, data):
    from .store import EXERCISES

    payload = dict(data)
    if "exercises" in payload:
        payload["exercises"] = [
            {**ex, "name": EXERCISES[ex["exercise_id"]]["name"]} for ex in payload["exercises"]
        ]
    upsert(
        con,
        "entry:" + identifier,
        kind,
        data["date"],
        kind + " " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )


def cosine(left, right):
    if len(left) != len(right):
        return 0
    denominator = math.sqrt(sum(v * v for v in left) * sum(v * v for v in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0


def scope_for(message, selected, previous=None):
    """Resolve explicit dates before inherited short-follow-up scope."""
    dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b", message)
    scope = dict(previous or {})
    if dates:
        for day in dates:
            date.fromisoformat(day)
        scope.update(start=min(dates), end=max(dates))
    elif re.search(r"\b(overall|all time|everything|entire history)\b", message, re.I):
        scope.pop("start", None)
        scope.pop("end", None)
    elif re.search(
        r"\b(today|yesterday|this week|last week|this month|last \d+ days)\b", message, re.I
    ):
        day = date.fromisoformat(selected)
        start = end = day
        if "yesterday" in message.lower():
            start = end = day - timedelta(days=1)
        elif "week" in message.lower():
            start = day - timedelta(days=day.weekday())
            if "last week" in message.lower():
                start -= timedelta(days=7)
                end = start + timedelta(days=6)
        elif "this month" in message.lower():
            start = day.replace(day=1)
        else:
            match = re.search(r"last (\d+) days", message, re.I)
            if match:
                start = day - timedelta(days=min(3660, max(1, int(match[1]))) - 1)
        scope.update(start=start.isoformat(), end=end.isoformat())
    kinds = set()
    for pattern, categories in (
        (r"workouts?|training|strength|exercises?", ["workout", "home_workout"]),
        (r"intake", ["meal", "creatine", "supplement", "sleep"]),
        (r"protein|calories|kcal|food|meals?|nutrition", ["meal"]),
        (
            ACTIVITY_PATTERN,
            ["cardio"],
        ),
        (r"creatine", ["creatine"]),
        (r"supplements?|vitamins?", ["supplement"]),
        (r"sleep|nap", ["sleep"]),
    ):
        source = (
            re.sub(r"\b(?:" + ACTIVITY_PATTERN + r")\b", " ", message, flags=re.I)
            if "workout" in categories
            else message
        )
        if re.search(r"\b(?:" + pattern + r")\b", source, re.I):
            kinds.update(categories)
    if kinds:
        scope["kinds"] = sorted(kinds)
        if (
            "home_workout" in kinds
            and re.search(r"\bhome\b", message, re.I)
            and not re.search(r"\bgym\b", message, re.I)
        ):
            scope["kinds"] = [kind for kind in scope["kinds"] if kind != "workout"]
        elif re.search(r"\bgym\b", message, re.I) and not re.search(r"\bhome\b", message, re.I):
            scope["kinds"] = [kind for kind in scope["kinds"] if kind != "home_workout"]
    if re.search(r"\b(everything|all categories|both|general|overall progress)\b", message, re.I):
        scope.pop("kinds", None)
    return scope


class SemanticIndex:
    def __init__(self, store, config=None):
        self.store, self.config = store, config or (lambda: {})
        self.enabled = False
        self.stop = threading.Event()
        self.worker = None
        self.cache = {}
        self.deadline = None
        self.busy = lambda: False

    def embed(self, texts, timeout=2):
        from .local_model import DEFAULT_URL, request

        cfg = self.config()
        result = request(
            cfg.get("ollama_url", DEFAULT_URL),
            "/api/embed",
            {
                "model": EMBED_MODEL,
                "input": [value[:3000] for value in texts],
                "truncate": False,
                "keep_alive": "10m",
            },
            timeout=timeout,
        )
        vectors = result.get("embeddings", [])
        if len(vectors) != len(texts) or any(
            not v or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v)
            for v in vectors
        ):
            raise ValueError("Invalid local embedding response")
        return vectors

    def index_pending(self, batch_size=16):
        with self.store.connect() as con:
            rows = con.execute(
                "SELECT id,content,digest FROM coach_chunks WHERE vector IS NULL OR model!=? LIMIT ?",
                (EMBED_MODEL, batch_size),
            ).fetchall()
        if not rows:
            return 0
        vectors = self.embed([r[1] for r in rows], timeout=20)
        with self.store.connect() as con:
            for (identifier, _, digest), vector in zip(rows, vectors):
                # A concurrent edit or deletion must never resurrect stale evidence.
                con.execute(
                    "UPDATE coach_chunks SET vector=?,model=? WHERE id=? AND digest=?",
                    (json.dumps(vector), EMBED_MODEL, identifier, digest),
                )
        return len(rows)

    def start(self):
        self.enabled = True

        def work():
            while not self.stop.is_set():
                if self.busy():
                    self.stop.wait(0.5)
                    continue
                try:
                    count = self.index_pending()
                except (ValueError, OSError):
                    count = 0
                self.stop.wait(0.05 if count else 5)

        self.worker = threading.Thread(target=work, daemon=True, name="coach-local-index")
        self.worker.start()

    def prefetch(self, queries):
        """Embed independent exercise terms in one batch, retaining source order."""
        missing = list(dict.fromkeys(q for q in queries if q and q not in self.cache))
        if not self.enabled or not missing:
            return
        remaining = self.deadline - time.monotonic() if self.deadline else 30
        if remaining <= 0.2:
            return
        try:
            vectors = self.embed(missing[:50], timeout=min(3, remaining))
            if len(self.cache) + len(vectors) > 128:
                self.cache.clear()
            self.cache.update(zip(missing, vectors))
        except (ValueError, OSError):
            # A failed embedding batch must not repeat its timeout per exercise.
            self.cache.update((query, None) for query in missing[:50])

    def search(self, query, *, category=None, scope=None, limit=6):
        scope = scope or {}
        conditions, args = [], []
        if category in ("exercise", "conversation"):
            conditions.append("category=?")
            args.append(category)
        else:
            conditions.append("category NOT IN ('exercise','conversation')")
        if scope.get("start"):
            conditions.append("day>=?")
            args.append(scope["start"])
        if scope.get("end"):
            conditions.append("day<=?")
            args.append(scope["end"])
        if scope.get("kinds"):
            conditions.append("category IN (" + ",".join("?" for _ in scope["kinds"]) + ")")
            args.extend(scope["kinds"])
        with self.store.connect() as con:
            rows = con.execute(
                "SELECT id,category,day,content,vector,model FROM coach_chunks WHERE "
                + " AND ".join(conditions),
                args,
            ).fetchall()
        vector = None
        remaining = self.deadline - time.monotonic() if self.deadline else 30
        if remaining > 0.2 and self.enabled and any(r[4] and r[5] == EMBED_MODEL for r in rows):
            try:
                if query not in self.cache:
                    if len(self.cache) >= 128:
                        self.cache.clear()
                    self.cache[query] = self.embed([query], timeout=min(2, remaining))[0]
                vector = self.cache[query]
            except (ValueError, OSError):
                pass
        words = set(re.findall(r"[a-z]{3,}", query.lower())) - {
            "the",
            "and",
            "for",
            "my",
            "what",
            "progress",
            "assess",
        }
        ranked = []
        for identifier, kind, day, content, raw, model in rows:
            overlap = len(words & set(re.findall(r"[a-z]{3,}", content.lower()))) / max(
                1, len(words)
            )
            semantic = (
                cosine(vector, json.loads(raw)) if vector and raw and model == EMBED_MODEL else 0
            )
            ranked.append(
                {
                    "id": identifier,
                    "kind": kind,
                    "date": day,
                    "content": content,
                    "score": round(semantic * 0.75 + overlap * 0.25, 4),
                    "retrieval": "semantic + keyword" if vector and raw else "keyword",
                }
            )
        ranked.sort(key=lambda r: (r["score"], r["date"]), reverse=True)
        return ranked[:limit]

    def search_exercises(self, query, *, limit=30, tracked=False, body_part=""):
        """Rank exact, fuzzy keyword and dense-vector matches for library pickers."""
        from difflib import SequenceMatcher

        from .exercise_matching import normalize
        from .store import CATALOG

        normalized = normalize(query)
        words = set(normalized.split()) - {"the", "for", "exercise", "with", "my"}
        if not words:
            return []
        allowed = None
        if tracked:
            allowed = {
                ex["exercise_id"]
                for entry in self.store.entries()
                if entry["kind"] in ("workout", "home_workout")
                and entry["date"] <= date.today().isoformat()
                for ex in entry["exercises"]
            }
        evidence = {
            row["id"].removeprefix("exercise:"): row
            for row in self.search(query, category="exercise", limit=len(CATALOG))
        }
        output = []
        for exercise in CATALOG:
            if allowed is not None and exercise["id"] not in allowed:
                continue
            if body_part and body_part not in exercise.get("bodyParts", exercise["primaryMuscles"]):
                continue
            names = [exercise["name"], *exercise.get("aliases", [])]
            fields = names + [
                " ".join(exercise["primaryMuscles"] + exercise.get("bodyParts", [])),
                exercise.get("equipment") or "",
            ]
            lexical = 0
            for field in fields:
                value = normalize(field)
                tokens = set(value.split())
                coverage = sum(
                    max((SequenceMatcher(None, word, token).ratio() for token in tokens), default=0)
                    for word in words
                ) / len(words)
                similarity = SequenceMatcher(None, normalized, value).ratio()
                lexical = max(lexical, 0.85 * coverage + 0.15 * similarity)
            exact = any(normalize(name) == normalized for name in names)
            row = evidence.get(exercise["id"], {})
            semantic = row.get("score", 0) if row.get("retrieval") == "semantic + keyword" else 0
            if lexical < 0.45 and semantic < 0.4:
                continue
            score = 0.7 * lexical + 0.3 * semantic + (0.3 if exact else 0)
            output.append(
                {
                    "id": exercise["id"],
                    "name": exercise["name"],
                    "score": round(score, 4),
                    "retrieval": "semantic + fuzzy keyword" if semantic else "fuzzy keyword",
                }
            )
        output.sort(key=lambda row: (-row["score"], len(row["name"]), row["name"]))
        if output:
            floor = max(0.4, output[0]["score"] - 0.22)
            output = [row for row in output if row["score"] >= floor]
        return output[:limit]
