"""LangGraph planner → bounded tools → response loop, with a draft-only finish."""

import math
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .agent_tools import TOOLS, public_query
from .coach_skills import select_skills
from .prompt_budget import build_messages


class AgentState(TypedDict, total=False):
    message: str
    context: dict
    catalog: list
    history: list
    skills: list
    reply: dict
    observations: list
    papers: list
    video_data: dict
    notices: list
    trace: list
    rounds: int
    searched: bool
    token_counts: list


def build_graph(coach, system, provider, model, key, budget):
    def model_node(state):
        messages, tokens = build_messages(
            system,
            TOOLS,
            state["skills"],
            state["context"],
            state["catalog"],
            state["history"],
            state["message"],
            state["observations"],
            budget,
            model,
        )
        coach.input_budget = budget
        reply = coach.generate(messages, provider, model, key)
        return {
            "reply": reply,
            "rounds": state["rounds"] + 1,
            "token_counts": state["token_counts"] + [tokens],
            "trace": state["trace"] + [{"node": "model", "input_tokens_estimate": tokens}],
        }

    def needs_calculator(state):
        question = state["message"]
        numeric_question = bool(
            re.search(r"\d", question)
            and re.search(
                r"percent|ratio|total|sum|convert|difference|multiply|divide|how (much|many)|[/+*=%]",
                question,
                re.I,
            )
        )
        has_result = any(
            o.get("tool") == "calculator" and "result" in o for o in state["observations"]
        )
        reply = state["reply"]
        proposal = reply.get("proposal")
        if reply.get("action") == "meal" and isinstance(proposal, dict):
            try:
                protein = float(proposal["protein"])
            except (KeyError, ValueError, TypeError):
                return False  # The normal proposal validator will reject malformed data.
            verified = any(
                o.get("tool") == "calculator"
                and "result" in o
                and math.isclose(protein, o["result"]["value"], abs_tol=0.05)
                for o in state["observations"]
            )
            if not verified:
                return True
        return numeric_question and reply.get("action") != "clarify" and not has_result

    def route(state):
        reply = state["reply"]
        if not state["searched"]:
            return "tools"
        if (reply.get("action") in ("tool", "research") or needs_calculator(state)) and state[
            "rounds"
        ] < 4:
            return "tools"
        return "finish"

    def tools_node(state):
        reply = state["reply"]
        calls = reply.get("tool_calls", []) if isinstance(reply.get("tool_calls", []), list) else []
        if reply.get("action") == "research":
            calls += [
                {
                    "name": "research",
                    "args": {"query": reply.get("research_query") or state["skills"][-1]["query"]},
                }
            ]
        if not state["searched"]:
            # A model cannot bypass the user's always-search requirement.
            calls = [
                {
                    "name": "web_search",
                    "args": {"query": reply.get("research_query") or state["skills"][-1]["query"]},
                }
            ] + [
                call
                for call in calls
                if isinstance(call, dict) and call.get("name") != "web_search"
            ]
        observations, papers, notices, trace = (
            list(state["observations"]),
            list(state["papers"]),
            list(state["notices"]),
            list(state["trace"]),
        )
        searched = state["searched"]
        if (
            searched
            and needs_calculator(state)
            and not any(isinstance(c, dict) and c.get("name") == "calculator" for c in calls)
        ):
            observations.append(
                {
                    "tool": "calculator",
                    "error": "Verify the arithmetic before answering. A meal draft protein total must equal an observed calculator result. Recalculate from your stated food quantities if assumptions changed; do not calculate mentally.",
                }
            )
        video = state.get("video_data")
        for call in calls[:3]:
            if len(observations) >= 8:
                notices.append("Tool-call limit reached for this turn.")
                break
            if not isinstance(call, dict):
                continue
            name, args = call.get("name"), call.get("args", {})
            if not isinstance(args, dict):
                args = {}
            if name == "web_search":
                searched = True
            try:
                if name in ("web_search", "research"):
                    args = {"query": public_query(args.get("query", ""))}
                result = coach.run_tool(name, args)
                if name in ("web_search", "research"):
                    papers += result
                    if any("metasearch unavailable" in item.get("kind", "") for item in result):
                        notices.append(
                            "Web metasearch was unavailable; used a live Europe PMC literature search instead."
                        )
                observations.append({"tool": name, "args": args, "result": result})
                trace.append(
                    {
                        "node": "tool",
                        "tool": name,
                        "args": args,
                        "ok": True,
                        **({"value": result["value"]} if name == "calculator" else {}),
                    }
                )
            except (ValueError, TypeError, KeyError) as error:
                notices.append(str(error))
                observations.append({"tool": name, "error": str(error)})
                trace.append({"node": "tool", "tool": name, "ok": False})
        return {
            "observations": observations,
            "papers": papers,
            "notices": notices,
            "trace": trace,
            "searched": searched,
            "video_data": video,
        }

    def finish(state):
        reply = dict(state["reply"])
        notices = list(state["notices"])
        if reply.get("action") in ("tool", "research") or needs_calculator(state):
            reply = {
                "action": "answer",
                "message": "I reached this turn’s tool limit. Please narrow the question so I can finish with the available evidence.",
            }
            notices.append("Agent stopped at its bounded reasoning limit; no proposal was created.")
        if not state["searched"]:
            raise ValueError("The coach could not complete its required web-search step.")
        return {
            "reply": reply,
            "notices": notices,
            "trace": state["trace"] + [{"node": "finish", "action": reply["action"]}],
        }

    builder = StateGraph(AgentState)
    builder.add_node("model", model_node)
    builder.add_node("tools", tools_node)
    builder.add_node("finish", finish)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", route, {"tools": "tools", "finish": "finish"})
    builder.add_edge("tools", "model")
    builder.add_edge("finish", END)
    return builder.compile()


def run_agent(coach, system, message, context, catalog, history, provider, model, key, budget):
    skills = select_skills(message, context["profile"]["focus"])
    graph = build_graph(coach, system, provider, model, key, budget)
    initial = {
        "message": message,
        "context": context,
        "catalog": catalog,
        "history": history,
        "skills": skills,
        "observations": [],
        "papers": [],
        "notices": [],
        "trace": [],
        "rounds": 0,
        "searched": False,
        "token_counts": [],
    }
    from langsmith.run_helpers import tracing_context

    with tracing_context(enabled=False):
        return graph.invoke(
            initial,
            {
                "recursion_limit": 16,
                "callbacks": [],
                "configurable": {},
                "tags": ["form-fuel-local-agent"],
            },
        )
