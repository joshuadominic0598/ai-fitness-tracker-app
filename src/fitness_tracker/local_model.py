"""Ollama text inference restricted to this computer, with bounded context and JSON replies."""

import ipaddress
import json
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


def request(base, path, payload=None, timeout=10):
    url = local_url(base) + path
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    # Do not route private local inference through a configured network proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read(2000)).get("error", "")
        except (ValueError, AttributeError):
            detail = ""
        raise ValueError(f"Ollama returned HTTP {error.code}. {detail}".strip()) from None
    except (OSError, json.JSONDecodeError):
        raise ValueError(
            "Ollama could not respond. Start Ollama on this Mac and check the local connection."
        ) from None


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
                "action": {"type": "string", "enum": ["meal", "clarify", "answer"]},
                "message": {"type": "string"},
                "proposal": {
                    "type": ["object", "null"],
                    "properties": {
                        "date": {"type": "string"},
                        "description": {"type": "string"},
                        "notes": {"type": "string"},
                        "low": {"type": "number"},
                        "high": {"type": "number"},
                        "items": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 50,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "portion": {"type": "string"},
                                    "calculation": {"type": "string"},
                                    "notes": {"type": "string"},
                                },
                                "required": ["name", "portion", "calculation", "notes"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["date", "description", "items"],
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
                    "workout",
                    "sleep",
                    "body",
                    "batch",
                    "plan",
                    "supplement",
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


def generate(messages, model, cfg, budget, *, direct=False, response_kind=None):
    from .agent_tools import calculator
    from .prompt_budget import input_tokens

    qwen_model(model)
    messages = [dict(message) for message in messages]
    meal_task = any(
        message["role"] == "system"
        and ("Meal:" in message["content"] or "Meal proposal:" in message["content"])
        for message in messages
    )
    if meal_task:
        messages[0]["content"] += (
            "\nLOCAL MEAL FORMAT: For each estimated food item include calculation, a numeric expression for that portion's protein (e.g. 150/100*3.3 for 150ml ordinary milk). The app evaluates these expressions and sums item protein locally; do not rely on mental arithmetic. On corrections, preserve untouched items and their protein values; a copied item can use its previous protein as a numeric literal calculation. Use supplied product labels and user-confirmed values first. Fallback reference assumptions only: ordinary dairy milk about 3.3g protein/100ml (8g per 240ml cup); cheddar-like cheese about 25g/100g (7g per 28g); a large whole egg about 6.3g. Special/high-protein milk and different cheeses vary: label your assumption. Never treat food weight as protein weight. Do not invent a label or say these cached references were just looked up."
        )
        if response_kind == "meal":
            messages[0]["content"] += (
                "\nFor this local meal schema, return ALL the foods as items with name, portion, calculation and assumption notes. Do not stop after the first food. Omit numeric protein fields: the app computes protein from each expression and the total itself. On a portion-only correction, copy every unchanged item and its previous protein as a literal calculation; do not drop or re-estimate it."
            )
    base = local_url(cfg.get("ollama_url", DEFAULT_URL))
    info = request(base, "/api/show", {"model": model})
    if info.get("remote_host") or info.get("remote_model") or model.endswith(":cloud"):
        raise ValueError(
            "Choose an installed local model; Ollama cloud models are not used by this connection."
        )
    if info.get("capabilities") and "completion" not in info["capabilities"]:
        raise ValueError("Choose a local chat model, not an embeddings-only model.")
    context = int(cfg.get("ollama_context_tokens", 8192))
    output = 2500 if response_kind == "workout" else 1800
    schema = response_schema(response_kind == "workout", direct, response_kind == "meal")
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
        "stream": False,
        "format": schema,
        "keep_alive": "5m",
        "options": {"num_ctx": context, "num_predict": output, "temperature": 0.2},
    }
    if "thinking" in info.get("capabilities", []):
        payload["think"] = False
    result = request(base, "/api/chat", payload, timeout=180)
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
    proposal = reply.get("proposal")

    def meal_total(data):
        items = data.get("items")
        if not isinstance(items, list) or not items:
            return None
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("The local meal breakdown needs a food object for each item.")
            if item.get("calculation"):
                item["protein"] = round(calculator(item["calculation"])["value"], 2)
        values = [float(item["protein"]) for item in items]
        total = round(sum(values), 2)
        data["protein"] = total
        # Do not display a model-produced range that excludes the computed sum.
        if not float(data.get("low", total)) <= total <= float(data.get("high", total)):
            data.pop("low", None)
            data.pop("high", None)
        data.pop("calculation", None)
        return "+".join(str(value) for value in values)

    if isinstance(proposal, dict) and reply.get("action") == "meal":
        expression = proposal.pop("calculation", reply.get("calculation"))
        reply["calculation"] = meal_total(proposal) or expression
    elif isinstance(proposal, dict) and reply.get("action") == "batch":
        for entry in proposal.get("entries", []):
            if entry.get("kind") == "meal":
                expression = meal_total(entry["data"])
                if expression:
                    entry["calculation"] = expression
    usage = {
        "input_tokens": actual,
        "output_tokens": result.get("eval_count", 0),
        "input_estimate": estimated,
        "context_tokens": context,
        "duration_ms": round(result.get("total_duration", 0) / 1_000_000),
    }
    return reply, usage
