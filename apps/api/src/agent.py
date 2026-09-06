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
You are the Covenant Certificate treasury copilot. You guide a finance reviewer
through an evidence-first covenant review.

Plan each turn from the user's request, current conversation, and latest tool
result. Choose the next tool dynamically; do not follow a fixed scripted sequence.
After a tool returns, decide whether another tool is justified or whether one
clarifying question is required. Never call a tool merely to imitate activity.

Use tools, do not guess:
- List cases when the user asks what is available or has not identified a case.
- Ingest a stored document when the user asks you to inspect an uploaded document.
- Process an uploaded document only after checking its declared document kind.
- Inspect current case state before describing progress or deciding the next tool.
- Run or reevaluate a case when the user asks for its calculation or current result.
- Never invent a clause, amount, formula, citation, status, or verdict.
- Treat credit_agreement and amendment uploads as agreement documents, and
  financial_statement uploads as financials. Do not ask the user to confirm an
  equivalent document-kind spelling that the application already supplied.

After each tool result, explain the result in plain language. For a calculation,
show the ratio, comparator, threshold, material inputs, and source limits. If a
required case id, document kind, period, or evidence item is missing, ask one short
question for that missing item. Do not ask questions that a tool result already
answers.

Human decisions are a hard boundary. If a result is NEEDS_REVIEW, explain the exact
blocker and ask the named reviewer to use the review card. Do not choose or submit a
review decision. Do not approve a package. Continue only after persisted state shows
that the human decision and deterministic recalculation completed.

All outputs are draft preparation. Never call them legal advice, an e-signature, a
signed certificate, or lender delivery. Do not reveal hidden reasoning. Keep answers
concise and evidence based. Prefer short sections and lists. Avoid wide Markdown
tables; the conversation panel is narrow.
"""


def ingest_covenant_document(case_id: str, document_id: str, document_kind: str) -> str:
    """Ingest a stored covenant document into a case by document ID.

    The document must already be stored via ``POST /api/cases/{case_id}/documents``.
    No filesystem paths are accepted: any ``document_id`` containing ``"/"``,
    ``"\\"``, or ``".."`` raises ``ValueError``. Bytes are resolved via
    ``DocumentService.read_bytes`` under the offline demo organization
    (``"demo-org"``) and run through the deterministic extraction module
    (``extract_aon_rule`` / ``extract_aon_financials``); stored bytes are
    spooled to a temporary file only because the extractors require a path,
    and the temp file is always deleted. Content the deterministic extractors
    cannot parse returns ``{"extraction_state": "unsupported", ...}`` without
    inventing figures. ``document_kind`` is ``'agreement'``, ``'financials'``,
    or ``'full-case'``.
    """
    kind = document_kind.lower()
    if "/" in document_id or "\\" in document_id or ".." in document_id:
        raise ValueError(
            f"document_id {document_id!r} must be a stored document identifier, "
            "not a filesystem path."
        )
    if kind not in ("agreement", "financials", "full-case"):
        raise ValueError(
            f"Unknown document_kind {document_kind!r}; expected 'agreement', "
            "'financials', or 'full-case'."
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

    def _document_service():
        try:
            import main as _main

            service = getattr(_main, "_documents", None)
            if service is not None:
                return service
        except Exception:
            pass
        from src.covenant.documents import DocumentService
        from src.covenant.revision_repository import (
            configured_database_url as revision_database_url,
        )
        from src.platform.storage import MemoryStorageAdapter

        return DocumentService(revision_database_url(), MemoryStorageAdapter())

    service = _document_service()
    _, content = service.read_bytes(document_id, "demo-org")

    import tempfile
    from pathlib import Path

    suffix = ".pdf" if kind == "agreement" else ".html"
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        if kind == "agreement":
            rule = extract_aon_rule(tmp_path)
            payload = {
                "case_id": case_id,
                "document_kind": "agreement",
                "document_id": rule.document_id,
                "source_document_id": document_id,
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
        facts = extract_aon_financials(tmp_path)
        return json.dumps(
            {
                "case_id": case_id,
                "document_kind": "financials",
                "source_document_id": document_id,
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
    except Exception as error:
        return json.dumps(
            {
                "case_id": case_id,
                "document_id": document_id,
                "document_kind": kind,
                "extraction_state": "unsupported",
                "reason": str(error),
            }
        )
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


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
    def run_covenant_case(case_id: str) -> str:
        """Run deterministic covenant arithmetic and the evidence review gate."""
        result = workflow.run(case_id, RunRequest())
        return result.model_dump_json(exclude={"trace": {"__all__": {"artifact_hash"}}})

    _ingest_impl = globals()["ingest_covenant_document"]

    @tool
    def ingest_covenant_document(
        case_id: str, document_id: str, document_kind: str
    ) -> str:
        """Ingest a stored covenant document into a case by document ID.

        document_id must be a stored document identifier, never a filesystem
        path (values containing "/", "\\", or ".." are rejected). document_kind is
        'agreement', 'financials', or 'full-case'. Bytes are resolved from the
        document store and parsed with the deterministic ingestion module;
        unparseable content returns extraction_state 'unsupported'.
        """
        return _ingest_impl(case_id, document_id, document_kind)

    @tool
    def reevaluate_covenant_case(case_id: str) -> str:
        """Re-run deterministic covenant evaluation after persisted input changes."""
        return reevaluate_case(workflow, case_id)

    @tool
    def inspect_case_state(case_id: str) -> str:
        """Read the authoritative persisted state for a private working case."""
        import main as application

        snapshot = application._active_revision_repository().snapshot(case_id)
        return json.dumps(snapshot, default=str)

    @tool
    def process_uploaded_document(case_id: str, document_id: str) -> str:
        """Queue durable analysis for one stored document in its current case.

        This tool does not calculate or approve anything. The worker emits
        persisted stage events and stops on missing evidence or human review.
        """
        import main as application

        location = application._documents.find_location(document_id)
        if str(location.get("case_id")) != case_id:
            raise ValueError("document does not belong to this case")
        head = application._active_revision_repository().current(case_id)
        store = application.app.state.durability_runtime.job_store
        try:
            job = store.enqueue(
                case_id,
                head.revision_id,
                {"document_id": document_id,
                 "version": location.get("version_number"),
                 "organization_id": location.get("organization_id")},
            )
        except Exception:
            existing = [job for job in application._jobs_for_case(store, case_id)
                        if job.revision_id == head.revision_id
                        and job.state in ("queued", "running", "waiting_review")]
            if not existing:
                raise
            job = existing[0]
        return json.dumps({"case_id": case_id, "document_id": document_id,
                           "revision_id": head.revision_id,
                           "job_id": job.id, "status": job.state})

    model = ChatOpenAI(
        model=os.getenv("LITELLM_STRONG_ALIAS", "covenant-strong"),
        api_key=api_key,
        base_url=os.getenv("LITELLM_BASE_URL") or None,
        temperature=0,
        model_kwargs={"parallel_tool_calls": False},
    )
    return create_agent(
        model=model,
        tools=[list_covenant_cases, inspect_case_state, ingest_covenant_document,
               process_uploaded_document, run_covenant_case,
               reevaluate_covenant_case],
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
