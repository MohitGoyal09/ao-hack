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
from langgraph.graph import END, START, MessagesState, StateGraph

from src.covenant import CovenantWorkflow, RunRequest
from src.covenant.ingestion import (
    build_aon_term_loan_case,
    extract_aon_financials,
    extract_aon_rule,
)
from src.platform.jobqueue import (
    durable_checkpointer,
)

SYSTEM_PROMPT = """
You are the Covenant Certificate treasury copilot. Help finance reviewers understand
the agreement-specific covenant workflow. Always call the supplied tools for case
facts and results; never invent a clause, financial amount, formula, or verdict.
Treat tool results as draft preparation only, surface every NEEDS_REVIEW blocker,
and remind the user that an authorized officer must review and sign the certificate.
Do not reveal hidden reasoning. Give concise evidence-based explanations.
"""


def ingest_document_for_case(case_id: str, document_path: str, document_kind: str) -> str:
    """Ingest a newly uploaded/referenced document into a case.

    Wraps the real PDF-ingestion module (extract_aon_rule /
    extract_aon_financials); never hand-types data. Returns real extracted
    data and citations as JSON.

    TODO(owner: versioning worker): once the CaseRevision/ChangeSet API in
    main.py + versioning module is ready, call it here to atomically create a
    new revision for this input change instead of returning extracted data
    only. Tracked follow-up: wire revision creation into this tool. Do not
    invent a parallel versioning path.
    """
    from pathlib import Path

    kind = document_kind.lower()
    path = Path(document_path)
    if kind == "agreement":
        rule = extract_aon_rule(path if str(path) not in ("", "default") else None)
        payload = {
            "case_id": case_id,
            "document_kind": "agreement",
            "document_id": rule.document_id,
            "document_title": rule.document_title,
            "document_hash": rule.document_hash,
            "rule": {
                "name": rule.name,
                "formula_label": rule.formula_label,
                "comparator": rule.comparator,
                "section": rule.section,
                "section_page": rule.section_page,
                "section_excerpt": rule.section_excerpt,
                "definition_page": rule.definition_page,
                "definition_excerpt": rule.definition_excerpt,
                "tiers": [
                    {"step": tier.step, "threshold": tier.threshold}
                    for tier in rule.tiers
                ],
            },
        }
        return json.dumps(payload)
    if kind == "financials":
        facts = extract_aon_financials(path if str(path) not in ("", "default") else None)
        return json.dumps(
            {
                "case_id": case_id,
                "document_kind": "financials",
                "facts": [
                    {
                        "key": fact.key,
                        "label": fact.label,
                        "amount": fact.amount,
                        "locator": fact.locator,
                    }
                    for fact in facts
                ],
            }
        )
    if kind == "full-case":
        case = build_aon_term_loan_case()
        return json.dumps(
            {
                "case_id": case.id,
                "name": case.name,
                "agreement": case.agreement,
                "test_date": case.test_date,
                "threshold": case.rule.threshold,
                "facts": [
                    {"key": fact.key, "amount": fact.amount, "locator": fact.source_locator}
                    for fact in case.facts
                ],
            }
        )
    raise ValueError(
        f"Unknown document_kind {document_kind!r}; expected 'agreement', 'financials', or 'full-case'."
    )


def reevaluate_case(
    workflow: CovenantWorkflow,
    case_id: str,
    reviewer_decision: str = "pending",
    reviewer_name: str | None = None,
    reviewer_rationale: str | None = None,
) -> str:
    """Trigger re-evaluation of a case after new input; returns real run JSON."""
    result = workflow.run(
        case_id,
        RunRequest(
            reviewer_decision=reviewer_decision,
            reviewer_name=reviewer_name,
            reviewer_rationale=reviewer_rationale,
        ),
    )
    return result.model_dump_json(exclude={"trace": {"__all__": {"artifact_hash"}}})


def build_agent_graph(workflow: CovenantWorkflow, *, checkpointer=None):
    """Compile against the application-owned checkpointer.

    The optional default is restricted to explicit offline use for legacy
    command-line callers; the FastAPI factory always supplies its live runtime.
    """
    checkpointer = checkpointer if checkpointer is not None else durable_checkpointer()
    api_key = os.getenv("LITELLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _build_offline_graph(workflow, checkpointer)

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

    @tool
    def ingest_covenant_document(
        case_id: str, document_path: str, document_kind: str
    ) -> str:
        """Ingest a newly uploaded/referenced document into a case.

        document_kind is 'agreement', 'financials', or 'full-case'.
        Parses the real source file with the deterministic ingestion module
        and returns extracted rules, facts, hashes, and citations.
        """
        return ingest_document_for_case(case_id, document_path, document_kind)

    @tool
    def reevaluate_covenant_case(
        case_id: str,
        reviewer_decision: str = "pending",
        reviewer_name: str | None = None,
        reviewer_rationale: str | None = None,
    ) -> str:
        """Re-run deterministic covenant evaluation for a case after new input."""
        return reevaluate_case(
            workflow, case_id, reviewer_decision, reviewer_name, reviewer_rationale
        )

    model = ChatOpenAI(
        model=os.getenv("LITELLM_STRONG_ALIAS", "covenant-strong"),
        api_key=api_key,
        base_url=os.getenv("LITELLM_BASE_URL") or None,
        temperature=0,
        model_kwargs={"parallel_tool_calls": False},
    )
    return create_agent(
        model=model,
        tools=[list_covenant_cases, run_covenant_case, ingest_covenant_document, reevaluate_covenant_case],
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )


def _build_offline_graph(workflow: CovenantWorkflow, checkpointer):
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
    return builder.compile(checkpointer=checkpointer)
