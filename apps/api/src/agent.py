"""Covenant-specialist LangGraph exposed over AG-UI.

With LiteLLM/OpenAI credentials the agent reasons conversationally and calls the
deterministic workflow as a tool. Without credentials a small deterministic graph
keeps the local demo usable and directs users through the curated cases.
"""

from __future__ import annotations

import json
import os

from langchain.agents import create_agent
from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from src.covenant import CovenantWorkflow, RunRequest


SYSTEM_PROMPT = """
You are the Covenant Certificate treasury copilot. Help finance reviewers understand
the agreement-specific covenant workflow. Always call the supplied tools for case
facts and results; never invent a clause, financial amount, formula, or verdict.
Treat tool results as draft preparation only, surface every NEEDS_REVIEW blocker,
and remind the user that an authorized officer must review and sign the certificate.
Do not reveal hidden reasoning. Give concise evidence-based explanations.
"""


def build_agent_graph(workflow: CovenantWorkflow):
    api_key = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _build_offline_graph(workflow)

    @tool
    def list_covenant_cases() -> str:
        """List covenant cases available for evidence-first analysis."""
        return json.dumps(workflow.list_cases())

    @tool
    def run_covenant_case(
        case_id: str,
        reviewer_decision: str = "pending",
        reviewer_name: str | None = None,
        reviewer_rationale: str | None = None,
    ) -> str:
        """Run deterministic covenant arithmetic and the evidence review gate."""
        result = workflow.run(
            case_id,
            RunRequest(
                reviewer_decision=reviewer_decision,
                reviewer_name=reviewer_name,
                reviewer_rationale=reviewer_rationale,
            ),
        )
        return result.model_dump_json(exclude={"trace": {"__all__": {"artifact_hash"}}})

    model = ChatOpenAI(
        model=os.getenv("LITELLM_STRONG_ALIAS", "covenant-strong"),
        api_key=api_key,
        base_url=os.getenv("LITELLM_BASE_URL") or None,
        temperature=0,
        model_kwargs={"parallel_tool_calls": False},
    )
    return create_agent(
        model=model,
        tools=[list_covenant_cases, run_covenant_case],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )


def _build_offline_graph(workflow: CovenantWorkflow):
    def respond(state: MessagesState) -> dict:
        message = str(state["messages"][-1].content).lower()
        matching = [case for case in workflow.list_cases() if case["id"] in message]
        if "list" in message or "case" in message and not matching:
            names = "\n".join(f"• {case['id']}: {case['name']}" for case in workflow.list_cases())
            content = f"Available evidence-first cases:\n{names}"
        elif matching:
            result = workflow.run(matching[0]["id"])
            content = (
                f"{matching[0]['name']}: {result.status.value}. "
                f"The deterministic ratio is {result.calculation.ratio:.2f}x against "
                f"{result.calculation.comparator} {result.calculation.threshold:.2f}x. "
                f"{result.status_reason} Authorized officer review is still required."
            )
        else:
            content = (
                "I can list the demo cases or run one by its case ID. Model-backed "
                "reasoning is disabled until LiteLLM credentials are configured."
            )
        return {"messages": [AIMessage(content=content)]}

    builder = StateGraph(MessagesState)
    builder.add_node("covenant_copilot", respond)
    builder.add_edge(START, "covenant_copilot")
    builder.add_edge("covenant_copilot", END)
    return builder.compile(checkpointer=MemorySaver())
