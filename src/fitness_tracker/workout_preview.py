"""Bounded workout interpretation with a usable preview even after model failures."""

import re

from .exercise_matching import canonical_id
from .store import EXERCISES, valid_date, validate
from .workout_notes import build_messages, clean_diary, inventory

BATCH_SIZE = 5


def prepare_workout(coach, source_text, selected_date, provider, model, key):
    """Retrieve per exercise, split model work, and ground quantities in source text."""
    from .coach import ProviderError

    source = inventory(source_text)
    stated_date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", source_text)
    selected_date = valid_date(stated_date[0] if stated_date else selected_date)
    groups = [group for group in source["groups"] if group["sets"]]
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
    exercises, matches, notices, token_counts, trace = [], [], [], [], []

    def handle(batch):
        ids = list(dict.fromkeys(eid for group in batch for eid in group["candidates"]))
        catalog = [
            {"id": eid, "name": EXERCISES[eid]["name"], "equipment": EXERCISES[eid]["equipment"]}
            for eid in ids
        ]
        batch_text = "\n".join(dict.fromkeys(s["source"] for group in batch for s in group["sets"]))
        try:
            messages, tokens = build_messages(
                "",
                batch_text,
                selected_date,
                catalog,
                coach.input_budget,
                model,
                provider,
                source={"groups": batch},
            )
        except ValueError:
            if len(batch) > 1:
                midpoint = len(batch) // 2
                handle(batch[:midpoint])
                handle(batch[midpoint:])
                return
            messages, tokens = [], 0
        generated = []
        try:
            if not messages:
                raise ValueError("Single movement exceeds model input budget")
            reply = coach.generate(
                messages, provider, model, key, direct=True, response_kind="workout"
            )
            if not isinstance(reply, dict):
                raise ValueError("Malformed workout response")
            proposal = reply.get("proposal")
            generated = proposal.get("exercises", []) if isinstance(proposal, dict) else []
            if not isinstance(generated, list):
                generated = []
        except (ProviderError, ValueError, TypeError, KeyError):
            notices.append(
                "The AI provider was unavailable or couldn't interpret one batch. This preview uses your explicitly supplied sets and suggested library matches; review the exercise variations before approving."
            )
        token_counts.append(tokens)
        trace.append(
            {
                "step": "workout_batch",
                "exercises": len(batch),
                "source_sets": sum(len(g["sets"]) for g in batch),
            }
        )
        for group in batch:
            choices = list(
                dict.fromkeys(
                    match
                    for item in generated
                    if isinstance(item, dict)
                    for match in [canonical_id(item.get("exercise_id"), group["candidates"])]
                    if match
                )
            )
            # A bad ID cannot invalidate the remaining workout. Each source
            # movement already has its own ranked, real library shortlist.
            # Broad aliases with no supplied variation use the conventional
            # first suggestion, rather than borrowing another source movement.
            eid = (
                choices[0]
                if len(choices) == 1
                and group["label"] not in ("triceps pushdown", "chest fly", "leg curl")
                else group["candidates"][0]
            )
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
            matches.append(f"{group['label']} → {EXERCISES[eid]['name']}")

    for start in range(0, len(groups), BATCH_SIZE):
        handle(groups[start : start + BATCH_SIZE])
    notes = "Exercise variations to review: " + "; ".join(matches) + ". Ask to change any match."
    if pending:
        notes += "\nNeeds clarification (not included in the sets above):\n" + "\n".join(pending)
    if exercises:
        reply = {
            "action": "workout",
            "message": "Review your workout and exercise matches.",
            "proposal": {"date": selected_date, "notes": notes, "exercises": exercises},
            "workout_prepared": True,
            "workout_incomplete": bool(pending),
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
        }
    return {
        "reply": reply,
        "papers": [],
        "skills": [],
        "trace": trace,
        "notices": list(dict.fromkeys(notices)),
        "token_counts": [n for n in token_counts if n],
    }
