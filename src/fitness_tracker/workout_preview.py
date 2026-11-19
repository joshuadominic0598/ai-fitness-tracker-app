"""Extract → retrieve → clarify → validate source sets without generative copying."""

import re

from .store import EXERCISES, valid_date, validate
from .workout_notes import clean_diary, inventory, movement_name

BATCH_SIZE = 5


def prepare_workout(coach, source_text, selected_date, provider, model, key):
    """Retrieve per movement; keep every stated set and ask about uncertain matches."""

    coach.stage("Reading each movement and keeping every repeated set…")
    extracted = inventory(source_text)
    retriever = getattr(coach, "retrieval", None)
    if retriever:
        coach.stage("Matching your exercise names in one local retrieval batch…")
        retriever.prefetch(
            [g["label"] for g in extracted["groups"]]
            + [movement_name(line) for line in extracted["unsupported"]]
        )
    source = inventory(source_text, retriever)
    stated_date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", source_text)
    selected_date = valid_date(stated_date[0] if stated_date else selected_date)
    groups = [group for group in source["groups"] if group["sets"]]
    ambiguous = [g for g in groups if g.get("requires_confirmation")]
    for group in groups:
        if re.search(r"\bstanding biceps? curls?\b", group["label"], re.I) and not re.search(
            r"dumbbell|barbell|cable", group["label"], re.I
        ):
            group["candidates"] = [
                "Dumbbell_Bicep_Curl",
                "Barbell_Curl",
                "Standing_Biceps_Cable_Curl",
            ]
            group["candidates"] = [eid for eid in group["candidates"] if eid in EXERCISES]
            if not group["candidates"] or group["candidates"][0] == "Barbell_Curl":
                group["candidates"].insert(0, "Dumbbell_Alternate_Bicep_Curl")
            if group not in ambiguous:
                ambiguous.append(group)
    groups = [g for g in groups if g not in ambiguous]
    pending = list(
        dict.fromkeys(
            [
                f"{item['source']}: "
                + (
                    "Was the bare number a weight in kg, a number of sets, or a machine plate/setting? If a setting, what kg does it represent?"
                    if "ambiguous" in item["reason"]
                    else "How many reps did you do at the stated load?"
                    if "Repetitions are missing" in item["reason"]
                    else item["reason"]
                )
                for item in source["unresolved"]
                if item.get("source")
            ]
            + [
                f"{line}: I couldn't confidently match this movement or parse its sets. Describe the movement or correct the name/quantities."
                for line in source["unsupported"]
            ]
        )
    )
    matching_choices = [
        {"label": group["label"], "candidates": group["candidates"][:3]} for group in ambiguous
    ]
    for group in ambiguous:
        retained = ", ".join(
            (
                f"{values['seconds']:g} sec"
                if values.get("seconds")
                else f"{values['weight']:g} kg × {values['reps']} reps"
            )
            for values in group["sets"]
        )
        names = [EXERCISES[eid]["name"] for eid in group["candidates"][:3]]
        pending.append(
            group["label"]
            + " (retained: "
            + retained
            + "). Which did you use? "
            + "; ".join(f"{i}. {name}" for i, name in enumerate(names, 1))
            + ". Your sets are retained."
        )
    exercises, trace = [], []

    def handle(batch):
        coach.stage(
            f"Checking {len(batch)} movements and {sum(len(g['sets']) for g in batch)} supplied sets…"
        )
        trace.append(
            {
                "step": "workout_batch",
                "exercises": len(batch),
                "source_sets": sum(len(g["sets"]) for g in batch),
            }
        )
        for group in batch:
            eid = group["candidates"][0]
            sets = [
                {"weight": s["weight"], "reps": s["reps"], "seconds": s.get("seconds", 0)}
                for s in group["sets"]
            ]
            exercise = {
                "exercise_id": eid,
                "tracking": "time" if sets[0]["seconds"] else "reps",
                "load_mode": "weighted" if any(s["weight"] for s in sets) else "bodyweight",
                "sets": sets,
            }
            try:
                validate("workout", {"date": selected_date, "exercises": [exercise]})
            except ValueError as error:
                pending.append(
                    f"{group['label']}: {error} Source: "
                    + " / ".join(dict.fromkeys(s["source"] for s in group["sets"]))
                )
                continue
            exercises.append(exercise)

    for start in range(0, len(groups), BATCH_SIZE):
        handle(groups[start : start + BATCH_SIZE])
    combined = {}
    for exercise in exercises:
        eid = exercise["exercise_id"]
        if eid in combined:
            combined[eid]["sets"].extend(exercise["sets"])
        else:
            combined[eid] = exercise
    exercises = list(combined.values())
    notes = ""
    if pending:
        notes += "Needs clarification (not included in the sets above):\n" + "\n".join(pending)
    if exercises:
        reply = {
            "action": "workout",
            "message": "Review your workout and exercise matches.",
            "proposal": {"date": selected_date, "notes": notes, "exercises": exercises},
            "workout_prepared": True,
            "source_set_count": sum(len(g["sets"]) for g in source["groups"]),
            "workout_incomplete": bool(pending),
            "matching_choices": matching_choices,
        }
    else:
        # Even with no valid sets there is still a source preview to correct.
        reply = {
            "action": "clarify",
            "message": "Workout preview — no sets are ready to save yet.\n\n"
            + ("\n".join(pending) or clean_diary(source_text))
            + "\n\nTell me the exercise names and missing reps, loads or durations. Nothing has been saved.",
            "proposal": None,
            "workout_prepared": True,
            "workout_incomplete": True,
            "matching_choices": matching_choices,
        }
    return {
        "reply": reply,
        "papers": [],
        "skills": [],
        "trace": trace,
        "notices": [],
        "token_counts": [],
    }
