"""Provider-native graph decisions with a final response function."""

from .agent_tools import TOOLS

FINAL_FUNCTION = "finish_coaching"


def direct_messages(messages, provider):
    return [dict(message) for message in messages]


def workout_final_schema():
    """One final formatter for completed workouts; no research/tool-routing actions."""
    schema = native_tool_schemas()[-1]
    parameters = schema["function"]["parameters"]
    parameters["properties"]["action"]["enum"] = ["workout", "clarify"]
    parameters["properties"].pop("proposal_json", None)
    parameters["properties"]["proposal"] = {
        "type": ["object", "null"],
        "properties": {
            "date": {"type": "string"},
            "duration": {"type": "number"},
            "notes": {"type": "string"},
            "exercises": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "exercise_id": {"type": "string"},
                        "tracking": {"type": "string", "enum": ["reps", "time"]},
                        "load_mode": {"type": "string", "enum": ["weighted", "bodyweight"]},
                        "sets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "weight": {"type": "number"},
                                    "reps": {"type": "integer"},
                                    "seconds": {"type": "number"},
                                },
                                "required": ["weight", "reps", "seconds"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["exercise_id", "tracking", "load_mode", "sets"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["date", "exercises"],
        "additionalProperties": False,
    }
    parameters["required"] = ["action", "message", "proposal"]
    return schema


def native_tool_schemas():
    tools = [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        name: {"type": "string", "description": description}
                        for name, description in tool["args"].items()
                    },
                    "required": list(tool["args"]),
                    "additionalProperties": False,
                },
            },
        }
        for tool in TOOLS
    ]
    tools.append(
        {
            "type": "function",
            "function": {
                "name": FINAL_FUNCTION,
                "description": "Finish this coaching turn with an answer, clarification or reviewable proposal. Never writes a journal entry.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "answer",
                                "clarify",
                                "meal",
                                "workout",
                                "sleep",
                                "body",
                                "batch",
                                "plan",
                                "supplement",
                                "creatine",
                            ],
                        },
                        "message": {"type": "string"},
                        "citations": {"type": "array", "items": {"type": "string"}},
                        "proposal": {
                            "type": ["object", "null"],
                            "additionalProperties": True,
                            "description": "The structured journal proposal, as a JSON object. Meal proposals include items:[{name,portion,protein,notes}] for every food/ingredient, plus the total protein and calculation. Prefer this over serialized proposal_json for direct chat.",
                        },
                        "proposal_json": {
                            "type": ["string", "null"],
                            "description": "A serialized proposal object following the meal/plan/supplement contract, or null.",
                        },
                    },
                    "required": ["action", "message"],
                    "additionalProperties": False,
                },
            },
        }
    )
    return tools
