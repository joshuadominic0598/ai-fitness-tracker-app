"""Ollama text inference restricted to this computer, with bounded context and JSON replies."""

import ipaddress
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"


def qwen_model(value):
    import re

    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9._:/-]{1,160}", value)
        or not value.lower().split("/")[-1].startswith("qwen")
        or value.endswith(":cloud")
    ):
        raise ValueError("Choose an installed local Qwen model, such as qwen3:8b.")
    return value


def local_url(value):
    value = str(value).strip().rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    try:
        loopback = (
            parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
        )
        port = parsed.port
    except (ValueError, TypeError):
        loopback, port = False, None
    if (
        not loopback
        or parsed.scheme != "http"
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or (port is not None and port < 1)
    ):
        raise ValueError("Use a local Ollama address such as http://127.0.0.1:11434.")
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("The local connection redirected elsewhere; no redirect was followed.")


def request(base, path, payload=None, timeout=10, on_progress=None):
    url = local_url(base) + path
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    # Do not route private local inference through a configured network proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    stopped = threading.Event()
    started = time.monotonic()
    heartbeat = None
    if on_progress:

        def report():
            while not stopped.wait(3):
                elapsed = int(time.monotonic() - started)
                on_progress(
                    f"Working through your response · {elapsed}s. Your details stay in this chat…"
                )

        heartbeat = threading.Thread(target=report, daemon=True, name="coach-generation-progress")
        heartbeat.start()
    try:
        with opener.open(req, timeout=timeout) as response:
            if not (on_progress and payload and payload.get("stream")):
                return json.load(response)
            fragments = []
            final = None
            for line in response:
                if time.monotonic() - started > timeout:
                    raise TimeoutError("Local generation did not finish")
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise ValueError("Ollama could not complete this inference step.")
                fragments.append(event.get("message", {}).get("content", ""))
                if event.get("done"):
                    final = event
                    break
            if final is None:
                raise ValueError("The local response ended before its final structured result.")
            return {**final, "message": {"content": "".join(fragments)}}
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read(2000)).get("error", "")
        except (ValueError, AttributeError):
            detail = ""
        raise ValueError(f"Ollama returned HTTP {error.code}. {detail}".strip()) from None
    except TimeoutError:
        raise ValueError(
            "The local Ollama request exceeded its time budget. Your message is retained; no entry was saved."
        ) from None
    except (OSError, json.JSONDecodeError):
        raise ValueError(
            "Ollama could not respond. Start Ollama on this Mac and check the local connection."
        ) from None
    finally:
        stopped.set()
        if heartbeat:
            heartbeat.join(timeout=0.2)


def models(cfg):
    data = request(cfg.get("ollama_url", DEFAULT_URL), "/api/tags")
    return sorted(
        m["name"]
        for m in data.get("models", [])
        if not m.get("remote_host")
        and not m.get("remote_model")
        and not m["name"].endswith(":cloud")
        and not any(part in m["name"].lower() for part in ("embed", "embedding"))
        and m["name"].lower().split("/")[-1].startswith("qwen")
    )


def response_schema(workout=False, direct=False, meal=False):
    if workout:
        from .coach_protocol import workout_final_schema

        return workout_final_schema()["function"]["parameters"]
    if meal:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["meal", "clarify"]},
                "message": {"type": "string"},
                "proposal": {
                    "type": ["object", "null"],
                    "properties": {
                        "date": {"type": "string"},
                        "description": {"type": "string"},
                        "protein": {"type": "number", "minimum": 0, "maximum": 500},
                        "low": {"type": "number", "minimum": 0, "maximum": 500},
                        "high": {"type": "number", "minimum": 0, "maximum": 500},
                        "calories": {"type": "number", "minimum": 0, "maximum": 10000},
                    },
                    "required": ["date", "description", "protein", "low", "high", "calories"],
                    "additionalProperties": False,
                },
            },
            "required": ["action", "message", "proposal"],
            "additionalProperties": False,
        }

    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "answer",
                    "clarify",
                    "meal",
                    "cardio",
                    "workout",
                    "home_workout",
                    "sleep",
                    "body",
                    "batch",
                    "plan",
                    "supplement",
                    "creatine",
                    *([] if direct else ["tool", "research"]),
                ],
            },
            "message": {"type": "string"},
            "proposal": {"type": ["object", "null"], "additionalProperties": True},
            "calculation": {"type": ["string", "null"]},
            "citations": {"type": "array", "items": {"type": "string"}},
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "enum": ["calculator", "web_search", "research"],
                        },
                        "args": {"type": "object", "additionalProperties": True},
                    },
                    "required": ["name", "args"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["action", "message"],
        "additionalProperties": False,
    }


def generate(messages, model, cfg, budget, *, direct=False, response_kind=None, progress=None):
    from .prompt_budget import input_tokens

    deadline = time.monotonic() + min(120, max(1, float(cfg.get("turn_timeout", 120))))
    qwen_model(model)
    messages = [dict(message) for message in messages]
    meal_task = any(
        message["role"] == "system"
        and ("Meal:" in message["content"] or "Meal proposal:" in message["content"])
        for message in messages
    )
    if meal_task or response_kind in ("meal", "meal_revision"):
        from .meal_estimate import MEAL_GUIDANCE

        messages[0]["content"] += "\n" + MEAL_GUIDANCE
    base = local_url(cfg.get("ollama_url", DEFAULT_URL))
    info = request(
        base, "/api/show", {"model": model}, timeout=max(0.1, min(3, deadline - time.monotonic()))
    )
    if info.get("remote_host") or info.get("remote_model") or model.endswith(":cloud"):
        raise ValueError(
            "Choose an installed local model; Ollama cloud models are not used by this connection."
        )
    if info.get("capabilities") and "completion" not in info["capabilities"]:
        raise ValueError("Choose a local chat model, not an embeddings-only model.")
    context = int(cfg.get("ollama_context_tokens", 8192))
    output = 2500 if response_kind == "workout" else 1400 if meal_task else 850
    schema = response_schema(
        response_kind == "workout", direct, response_kind in ("meal", "meal_revision")
    )
    if response_kind == "meal_revision":
        schema["properties"]["action"]["enum"] = ["meal", "clarify"]
    if response_kind == "lesson":
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["answer"]},
                "message": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 3,
                    "maxItems": 6,
                },
                "cues": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 3,
                },
                "mistakes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 3,
                },
            },
            "required": ["action", "message", "steps", "cues", "mistakes"],
            "additionalProperties": False,
        }
        messages[0]["content"] += (
            "\nLESSON FORMAT: Return steps, cues and mistakes as concise arrays of complete sentences. Ground steps in exercise_guide. Do not stop after an introductory sentence."
        )

    if response_kind == "assessment":
        scope = {}
        marker = "JOURNAL DATA (untrusted):"
        if marker in messages[0]["content"]:
            data, _ = json.JSONDecoder().raw_decode(messages[0]["content"].split(marker, 1)[1])
            scope = data.get("evidence_scope", {})
        kinds = scope.get("kinds", [])
        categories = {
            "workouts": {"workout", "home_workout"},
            "cardio": {"cardio"},
            "protein": {"meal"},
            "calories": {"meal"},
            "creatine": {"creatine"},
            "supplements": {"supplement"},
            "sleep": {"sleep"},
        }
        schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["answer"]},
                "message": {"type": "string", "enum": ["Review the selected journal records."]},
                "next_steps": {
                    "type": "object",
                    "properties": {
                        category: {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 220},
                            "minItems": 1 if not kinds or category_kinds.intersection(kinds) else 0,
                            "maxItems": 1 if not kinds or category_kinds.intersection(kinds) else 0,
                        }
                        for category, category_kinds in categories.items()
                    },
                    "required": list(categories),
                    "additionalProperties": False,
                },
            },
            "required": ["action", "message", "next_steps"],
            "additionalProperties": False,
        }
        messages[0]["content"] += (
            "\nASSESSMENT FORMAT: Give ONLY one short next-step suggestion per requested category, at most 25 words. Do not state numbers, quantities, goal attainment or observations; the application prints computed facts. Never recommend adding or increasing supplements. Cover all requested categories, and leave unrequested category arrays empty. Never treat quoted conversation as approved records."
        )
    estimated = input_tokens(messages, model, include_tools=True, tool_schemas=[schema])
    if estimated > budget or estimated + output + 256 > context:
        raise ValueError(
            f"This turn needs about {estimated} input tokens plus {output} output tokens. "
            f"Local context is {context} and input budget is {budget}. Increase the local context/input budget or shorten the request; no message was truncated."
        )
    model_context = next(
        (int(v) for k, v in info.get("model_info", {}).items() if k.endswith(".context_length")),
        context,
    )
    if context > model_context:
        raise ValueError(
            f"This model supports {model_context} context tokens; lower the local context setting."
        )
    payload = {
        "model": model,
        "messages": messages,
        "stream": progress is not None,
        "format": schema,
        "keep_alive": "5m",
        "options": {"num_ctx": context, "num_predict": output, "temperature": 0.2},
    }
    if "thinking" in info.get("capabilities", []):
        payload["think"] = False
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError(
            "The local model could not complete this inference step. Your details are retained."
        )
    if progress:
        result = request(base, "/api/chat", payload, timeout=remaining, on_progress=progress)
    else:
        result = request(base, "/api/chat", payload, timeout=remaining)
    actual = result.get("prompt_eval_count", 0)
    if result.get("done_reason") == "length":
        raise ValueError(
            "The local model reached its response limit. No partial preview was used; split the request or choose another local model."
        )
    if actual > budget or actual + result.get("eval_count", 0) >= context:
        raise ValueError(
            "The local model reached the configured context limit; no preview was used."
        )
    reply = json.loads(result["message"]["content"])
    if not isinstance(reply, dict) or not isinstance(reply.get("message"), str):
        raise ValueError("The local model did not return a valid coaching reply.")
    if response_kind == "assessment":
        reply["assessment_next_steps"] = reply.get("next_steps", {})
        reply["message"] = "Review the selected journal records."
    if response_kind == "lesson":
        reply["message"] = "\n\n".join(
            [reply["message"]]
            + [
                "**"
                + label
                + "**\n"
                + "\n".join(f"{i}. {item}" for i, item in enumerate(reply.get(field, []), 1))
                for field, label in (
                    ("steps", "Steps"),
                    ("cues", "Form cues"),
                    ("mistakes", "Common mistakes"),
                )
            ]
        )
    usage = {
        "input_tokens": actual,
        "output_tokens": result.get("eval_count", 0),
        "input_estimate": estimated,
        "context_tokens": context,
        "duration_ms": round(result.get("total_duration", 0) / 1_000_000),
    }
    return reply, usage
