"""Bounded public search and a numeric-only calculator; no arbitrary code or URL fetch."""

import ast
import ipaddress
import math
import operator
import re
from urllib.parse import urlsplit

from .coach_skills import MANIFEST

TOOLS = [
    {
        "name": "web_search",
        "args": {"query": "general public exercise/nutrition topic"},
        "description": "Search the web. Mandatory before answering. No private journal facts in queries.",
    },
    {
        "name": "research",
        "args": {"query": "general evidence topic"},
        "description": "Find research abstracts through Europe PMC.",
    },
    {
        "name": "calculator",
        "args": {"expression": "numeric arithmetic expression"},
        "description": "Use for ALL arithmetic, ratios, percentages, conversions and totals. No code or variables.",
    },
]


PUBLIC_WORDS = set(
    re.findall(
        r"[a-z]+", " ".join(item["query"] + " " + " ".join(item["keywords"]) for item in MANIFEST)
    )
) | set(
    "exercise nutrition protein portion food chicken egg eggs rice milk yogurt dal lentils beans tofu fish portions vegetables vegan vegetarian healthy adults women men older biomechanics anatomy muscles biceps triceps forearm forearms chest upper lower back lats legs thighs quadriceps hamstrings calf calves glutes shoulder shoulders abdominal abs bodyweight plank pullups pull ups pushups squat bench press row cable dumbbell barbell incline decline neutral grip wrist curl pull down lat technique form safety range motion load volume sets repetitions frequency aerobic endurance recovery sleep rest soreness stretching muscle hypertrophy systematic review meta analysis randomized trial evidence guidelines position stand creatine monohydrate supplements vitamin vitamins collagen b12 fish oil dosage units consumption performance energy strength progress training periodization health balance stability walking cycling running swimming beginner intermediate advanced full body strength arms diet cardio repetitions per week daily warm up resistance fatigue pain physical activity breathing hydration adherence consistency goal target high intensity interval moderate vigorous ACSM WHO NIH ISSN IUSCA CDC NHS pubmed evidence based".lower().split()
)


def public_query(value):
    if not isinstance(value, str):
        raise ValueError("Enter a public fitness topic.")
    words = [word for word in re.findall(r"[a-z]+", value.casefold()) if word in PUBLIC_WORDS]
    return " ".join(words[:18]) or "exercise training nutrition evidence guidelines"


def safe_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return False
    if parsed.hostname == "localhost" or parsed.hostname.endswith((".local", ".localhost")):
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_global
    except ValueError:
        return "." in parsed.hostname


def web_search(query):
    from ddgs import DDGS

    query = public_query(query)
    try:
        results = DDGS(timeout=5).text(query, max_results=5, backend="bing")
        output = []
        for item in results:
            url = item.get("href", "")
            if safe_url(url):
                output.append(
                    {
                        "title": str(item.get("title", ""))[:180],
                        "url": url,
                        "abstract": str(item.get("body", ""))[:1000],
                        "kind": "web search snippet",
                    }
                )
        if not output:
            raise ValueError("No web results.")
        primary = (
            "acsm.org",
            "who.int",
            "nih.gov",
            "cdc.gov",
            "nhs.uk",
            "nsca.com",
            "jissn.biomedcentral.com",
            "journal.iusca.org",
        )
        output.sort(
            key=lambda item: (
                not any(
                    urlsplit(item["url"]).hostname == domain
                    or urlsplit(item["url"]).hostname.endswith("." + domain)
                    for domain in primary
                )
            )
        )
        return output
    except Exception:
        # A public scholarly search is a useful live fallback, not a pretend web result.
        from .coach import research

        try:
            return [
                {**item, "kind": "live literature search · metasearch unavailable"}
                for item in research(query)
            ]
        except ValueError as error:
            raise ValueError(
                "Live web and literature search are unavailable. Cached skill sources are not fresh search results."
            ) from error


def calculator(expression):
    if not isinstance(expression, str) or len(expression) > 300:
        raise ValueError("Use a numeric expression of at most 300 characters.")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError):
        raise ValueError("Enter a valid numeric expression.") from None
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("Calculation is too complex.")
    ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    funcs = {"round": round, "abs": abs, "min": min, "max": max, "sqrt": math.sqrt}

    def evaluate(node, depth=0):
        if depth > 15:
            raise ValueError("Calculation is too deeply nested.")
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            result = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = evaluate(node.operand, depth + 1) * (
                -1 if isinstance(node.op, ast.USub) else 1
            )
        elif isinstance(node, ast.BinOp) and type(node.op) in ops:
            left, right = evaluate(node.left, depth + 1), evaluate(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent is too large.")
            result = ops[type(node.op)](left, right)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in funcs
            and not node.keywords
            and 1 <= len(node.args) <= 8
        ):
            result = funcs[node.func.id](*[evaluate(arg, depth + 1) for arg in node.args])
        else:
            raise ValueError("Only numeric arithmetic is allowed.")
        if not isinstance(result, (int, float)) or not math.isfinite(result) or abs(result) > 1e12:
            raise ValueError("Calculation is outside the supported range.")
        return result

    try:
        result = evaluate(tree.body)
    except (ZeroDivisionError, OverflowError, TypeError):
        raise ValueError("Calculation could not be completed.") from None
    return {"expression": expression, "value": result}
