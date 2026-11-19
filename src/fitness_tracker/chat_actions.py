"""Application-owned action receipts, independent of the selected language model."""

import re
from copy import deepcopy
from decimal import Decimal


def meal_portion_revision(message, original):
    """Apply one explicit portion-only correction without re-estimating other foods."""
    if not re.match(r"\s*(?:change|update|correct|set|make)\b", message, re.I):
        return None
    clause = re.split(
        r",?\s+\b(?:keeping|keep|leaving|leave|preserving|preserve)\b",
        message,
        maxsplit=1,
        flags=re.I,
    )[0]
    if re.search(
        r"\b(?:add|remove|delete|replace|instead|also|and|protein|brand|type)\b", clause, re.I
    ):
        return None
    quantities = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(ml|kg|g|l)\b", clause, re.I))
    if len(quantities) != 1:
        return None
    new = quantities[0]
    items = original.get("items", [])
    matches = []
    for index, item in enumerate(items):
        words = set(re.findall(r"[a-z]{3,}", item["name"].lower())) - {
            "whole",
            "large",
            "boiled",
            "cooked",
            "raw",
            "food",
        }
        if any(re.search(r"\b" + re.escape(word) + r"\b", clause, re.I) for word in words):
            matches.append(index)
    if len(matches) != 1:
        return None
    index = matches[0]
    old = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ml|kg|g|l)\s*", items[index]["portion"], re.I)
    if not old or float(old[1]) <= 0 or float(new[1]) <= 0:
        return None
    scales = {"ml": ("volume", 1), "l": ("volume", 1000), "g": ("mass", 1), "kg": ("mass", 1000)}
    old_unit, new_unit = old[2].lower(), new[2].lower()
    if scales[old_unit][0] != scales[new_unit][0]:
        return None
    ratio = float(new[1]) * scales[new_unit][1] / (float(old[1]) * scales[old_unit][1])
    result = deepcopy(original)
    changed = result["items"][index]
    changed["portion"] = f"{float(new[1]):g} {new_unit}"
    changed["protein"] = round(float(changed["protein"]) * ratio, 2)
    result["protein"] = round(sum(float(item["protein"]) for item in result["items"]), 2)
    delta = result["protein"] - float(original["protein"])
    for bound in ("low", "high"):
        if bound in result:
            result[bound] = round(max(0, float(result[bound]) + delta), 2)
    result["description"] = ", ".join(
        f"{item['portion']} {item['name']}" for item in result["items"]
    )
    result["notes"] = (
        result.get("notes", "")
        + f"\n{changed['name']} changed from {items[index]['portion']} to {changed['portion']}; other food estimates retained."
    ).strip()
    return result


def pending_revision(message, history, drafts):
    """Keep a correction attached to its pending chat action across every log category."""
    if not re.match(
        r"\s*(?:(?:please|actually)[,! ]+)?(?:change|correct|update|revise|instead|make it|set it|move it)\b",
        message,
        re.I,
    ) or re.search(r"\b(goals?|settings?|connections?|models?|api keys?)\b", message, re.I):
        return None
    reference = next(
        (
            m["draft"]["id"]
            for m in reversed(history)
            if m.get("role") == "assistant" and m.get("draft")
        ),
        None,
    )
    draft = next((d for d in drafts if d["id"] == reference), None)
    if not draft:
        return None
    from .prompt_budget import chat_topics

    kinds = (
        {e["kind"] for e in draft["data"]["entries"]}
        if draft["kind"] == "batch"
        else {draft["kind"]}
    )
    topics = {{"workout": "training", "plan": "training"}.get(k, k) for k in kinds}
    current = chat_topics(message) - {"assessment"}
    return draft["id"] if not current or current <= topics else None


def requested_log_kind(message, history=()):
    """Recognize a request to prepare data, including short conversational follow-ups."""
    if not re.match(
        r"^\s*(?:(?:ya|yeah|yes|ok|okay|please|sure)[,! .]+)*"
        r"(?:(?:can|could|would) you\s+|help me\s+|i (?:want|would like) (?:you )?to\s+)?"
        r"(?:log\b|add\b|record\b|save\b|prepare\b.{0,35}\b(?:preview|entry|log|draft)\b)",
        message,
        re.I,
    ) or re.search(r"\b(?:don't|do not|not yet|instead of)\b", message, re.I):
        return None
    from .prompt_budget import chat_topics

    for value in [message] + [m.get("text", "") for m in reversed(history[-6:])]:
        topics = chat_topics(value) - {"assessment"}
        if topics:
            if len(topics) > 1:
                return "any"
            topic = topics.pop()
            return {"training": "workout"}.get(topic, topic)
    return "any"


def check_meal_calculation(proposal, expression):
    """Accept exact arithmetic or rounding to the precision of the displayed estimate."""
    from .agent_tools import calculator

    value = calculator(expression)["value"]
    protein = float(proposal["protein"])
    # Estimated totals such as 17.8 g -> 18 g are legitimate rounding, not failed math.
    precision = max(0, -Decimal(str(protein)).normalize().as_tuple().exponent)
    if abs(value - protein) > 0.05 and round(value, precision) != protein:
        raise ValueError("Protein total does not match the breakdown.")


def draft_summary(draft):
    """Describe only validated proposal data; the model cannot invent a write receipt."""
    items = (
        draft["data"]["entries"]
        if draft["kind"] == "batch"
        else [{"kind": draft["kind"], "data": draft["data"]}]
    )
    parts = []
    for item in items:
        kind, data = item["kind"], item["data"]
        if kind == "meal":
            description = data["description"]
            if len(description) > 100:
                description = description[:97] + "…"
            parts.append(f"{data['protein']:g} g protein ({description})")
            if data.get("low") is not None and data.get("high") is not None:
                parts[-1] += f"; estimated range {data['low']:g}–{data['high']:g} g"
        elif kind in ("supplement", "creatine"):
            parts.append(f"{data['name']}: {data['amount']:g} {data['unit']}")
        elif kind == "sleep":
            period = {"night": "night sleep", "afternoon": "afternoon nap", "other": "nap"}
            parts.append(f"{data['hours']:g} h {period[data['period']]}")
        elif kind == "body":
            parts.append(f"{data['weight_kg']:g} kg body weight")
        else:
            exercises = data["exercises"]
            count = len(exercises)
            exercise_label = f"{count} exercise{'s' if count != 1 else ''}"
            if kind == "plan":
                parts.append(f"a session plan with {exercise_label}")
            else:
                sets = [s for e in exercises for s in e["sets"]]
                parts.append(f"{exercise_label}, {len(sets)} set{'s' if len(sets) != 1 else ''}")
    return f"Prepared for {items[0]['data']['date']}: " + "; ".join(parts) + "."


def draft_message(draft):
    """Print reviewable item details in chat, independently of disclosure controls."""
    from .store import EXERCISES

    items = (
        draft["data"]["entries"]
        if draft["kind"] == "batch"
        else [{"kind": draft["kind"], "data": draft["data"]}]
    )
    incomplete = any(
        item["kind"] == "workout"
        and "Needs clarification (not included" in item["data"].get("notes", "")
        for item in items
    )
    sections = (
        ["**Partial workout preview** — resolve the questions below before approval."]
        if incomplete
        else []
    ) + [draft_summary(draft)]
    for item in items:
        if item["kind"] == "meal":
            data = item["data"]
            lines = [
                f"{index}. {food['name']} ({food['portion']}): ≈{food['protein']:g} g protein"
                + (f" — {food['notes']}" if food.get("notes") else "")
                for index, food in enumerate(data.get("items", []), 1)
            ]
            if lines:
                lines.append(f"\nTotal: ≈{data['protein']:g} g protein")
                if "low" in data and "high" in data:
                    lines.append(f"Estimated range: {data['low']:g}–{data['high']:g} g")
            if data.get("notes"):
                lines.append("Assumptions: " + data["notes"])
            if lines:
                sections.append("\n".join(lines))
            continue
        if item["kind"] not in ("workout", "plan"):
            if item["data"].get("notes"):
                note = "**Note:** " + item["data"]["notes"]
                if note not in sections:
                    sections.append(note)
            if item["kind"] == "sleep" and item["data"].get("continuous_hours"):
                sections.append(
                    f"Uninterrupted: {item['data']['continuous_hours']:g} h. Optional: add notes before approval."
                )
            continue
        data = item["data"]
        lines = []
        for index, exercise in enumerate(data["exercises"], 1):
            name = EXERCISES[exercise["exercise_id"]]["name"]
            lines.append(f"{index}. **{name}**")
            for set_index, values in enumerate(exercise.get("sets", []), 1):
                load = f"{values['weight']:g} kg" if values["weight"] else "Bodyweight"
                quantity = (
                    f"{values['seconds']:g} sec"
                    if values.get("seconds")
                    else f"{values['reps']} reps"
                )
                lines.append(f"   Set {set_index}: {load} × {quantity}")
        if data.get("notes"):
            notes = data["notes"]
            if "Needs clarification (not included in the sets above):" in notes:
                _, questions = notes.split(
                    "Needs clarification (not included in the sets above):", 1
                )
                lines.append(
                    "\n**Needs clarification**\n"
                    + "\n".join(
                        f"{i}. {question}"
                        for i, question in enumerate(questions.strip().splitlines(), 1)
                    )
                )
            elif notes:
                lines.append("\n**Notes:** " + notes)
        sections.append("\n".join(lines))
    sections.append(
        "Tell me what to change, or approve it here when everything looks right. "
        "Nothing is saved until you approve."
    )
    return "\n\n".join(sections)


def approve_from_chat(store, message, history, draft_id=None):
    """Approve only an explicit confirmation of a preview linked in recent chat."""
    if not re.fullmatch(
        r"\s*(?:(?:yes|ok|okay)[,!. ]+)?(?:i approve(?: it| this| the preview)?|approve(?: it| this| the preview)?|(?:save|log) (?:it|this|the preview))(?:[,! .]+please)?[.! ]*\s*",
        message,
        re.I,
    ):
        return None
    references = store.messages() if draft_id else history
    reference = next(
        (
            m["draft"]["id"]
            for m in reversed(references)
            if m.get("role") == "assistant"
            and m.get("draft")
            and (draft_id is None or m["draft"]["id"] == draft_id)
        ),
        None,
    )
    draft = next((d for d in store.drafts() if d["id"] == reference), None)
    if reference is None and draft_id is None and re.search(r"\blog\b", message, re.I):
        return None  # A request to log an estimate still needs a structured draft first.
    if not draft:
        return {
            "action": "answer",
            "text": "There is no pending preview linked to this conversation to approve. Nothing was saved. Ask me to prepare the entry, or open its pending preview in Track.",
        }
    result = store.approve(draft["id"])
    entries = result.get("entries", [result])
    day = entries[0]["date"]
    return {
        "action": "approved",
        "text": draft_summary(draft).replace("Prepared for", "Approved and saved for", 1)
        + " You can review or edit them in Track.",
        "approved": {"draft_id": draft["id"], "date": day, "entries": entries},
    }


def claims_saved(message):
    """Models cannot issue successful write receipts; only actual app actions can."""
    for match in re.finditer(
        r"\b(?:i(?:'ve| have)?|we(?:'ve| have)?)\s+(?:(?:successfully|now|already)\s+)*(?:logged|saved|recorded|approved)\b"
        r"|\b(?:has been|have been|is|are)\s+(?:(?:now|successfully|already)\s+)*(?:saved|recorded|logged|approved)\b",
        message,
        re.I,
    ):
        clause = re.split(r"[.!?\n]", message[: match.start()])[-1]
        if not re.search(
            r"\b(?:nothing|no (?:entry|entries|data|record)|when|once|after|before|until|if)\b",
            clause,
            re.I,
        ):
            return True
    return False
