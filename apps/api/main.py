"""FastAPI and AG-UI adapters for Covenant Certificate."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Annotated

from dotenv import load_dotenv

load_dotenv()

# Neatlogs must initialize before LangGraph/provider imports.
from src.platform.observability import NeatlogsObserver

observer = NeatlogsObserver.from_env()
observer.initialize()

from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.agent import build_agent_graph
from src.covenant import RunRequest, UnknownCaseError, build_demo_workflow
from src.covenant.revisions import (
    IdempotencyConflictError,
    StaleCommandError,
    UnknownRevisionError,
    store as revision_store,
)
from src.platform.supabase import (
    AuthenticationError,
    PersistenceError,
    Principal,
    SupabasePlatform,
)

workflow = build_demo_workflow()
platform = SupabasePlatform.from_env()
agent_graph = build_agent_graph(workflow)


def _ensure_revisions(case_id: str) -> None:
    try:
        case = workflow._repository.get_case(case_id)  # noqa: SLF001
    except UnknownCaseError:
        raise HTTPException(status_code=404, detail="Unknown covenant case")
    revision_store.ensure_case(
        case_id=case.id,
        test_date=case.test_date,
        rule_id=case.rule.id,
        threshold=case.rule.threshold,
        doc_ids=[d.id for d in case.documents],
        fact_keys=[f.key for f in case.facts],
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    observer.shutdown()


app = FastAPI(
    title="Covenant Certificate API",
    version="0.2.0",
    description="Evidence-first covenant workflow with LangGraph and AG-UI.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["authorization", "content-type"],
)


async def current_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    try:
        return await asyncio.to_thread(platform.authenticate, authorization)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "covenant-certificate",
        "orchestrator": workflow.engine_name,
        "supabase": "configured" if platform.enabled else "offline-demo",
        "neatlogs": "configured" if observer.enabled else "disabled",
        "agent_transport": "ag-ui",
    }


@app.get("/api/demo-cases")
async def demo_cases() -> list[dict]:
    return workflow.list_cases()


@app.get("/api/cases/{case_id}")
async def get_case(case_id: str) -> dict:
    try:
        return workflow.describe(case_id)
    except UnknownCaseError as error:
        raise HTTPException(status_code=404, detail="Unknown covenant case") from error


@app.post("/api/cases/{case_id}/run")
async def run_case(
    case_id: str,
    request: RunRequest = RunRequest(),
    principal: Principal = Depends(current_principal),
) -> dict:
    try:
        with observer.workflow_span(case_id):
            result = await asyncio.to_thread(
                workflow.run, case_id, request, observer.callbacks()
            )
            observer.record_outcome(case_id, result.run_id, result.status.value)
        artifact_path = await asyncio.to_thread(
            platform.persist_run, result, principal
        )
    except UnknownCaseError as error:
        raise HTTPException(status_code=404, detail="Unknown covenant case") from error
    except PersistenceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    payload = result.model_dump(mode="json")
    payload["runtime"] = {
        "orchestrator": workflow.engine_name,
        "persistence": "supabase" if platform.enabled else "in-memory demo",
        "artifact_path": artifact_path,
    }
    return payload


@app.get("/api/cases/{case_id}/history")
async def case_history(
    case_id: str, _: Principal = Depends(current_principal)
) -> list[dict]:
    try:
        return workflow.history(case_id)
    except UnknownCaseError as error:
        raise HTTPException(status_code=404, detail="Unknown covenant case") from error


@app.post("/api/cases/{case_id}/revisions")
async def create_revision(case_id: str, body: dict) -> dict:
    _ensure_revisions(case_id)
    try:
        rev, changeset, impact = revision_store.create_revision(
            case_id=case_id,
            expected_parent=str(body.get("expected_parent_revision", "")),
            change_kind=str(body.get("change_kind", "amendment")),
            documents=list(body.get("documents", [])),
            facts=list(body.get("facts", [])),
            new_threshold=body.get("new_threshold"),
        )
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StaleCommandError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "revision_id": rev.revision_id,
        "revision": rev.model_dump(mode="json"),
        "changeset": changeset.model_dump(mode="json"),
        "impact_pending": impact.model_dump(mode="json"),
    }


@app.get("/api/cases/{case_id}/revisions/{revision_id}/impact")
async def revision_impact(case_id: str, revision_id: str) -> dict:
    _ensure_revisions(case_id)
    try:
        rev = revision_store.get(case_id, revision_id)
        impact = revision_store.impact(case_id, revision_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "revision_id": rev.revision_id,
        "changed_inputs": impact.changed_definitions,
        "affected_rule_ids": impact.affected_rule_ids,
        "stale_artifact_ids": impact.stale_artifact_ids,
        "review_requirements": impact.review_requirements,
        "impact": impact.model_dump(mode="json"),
    }


@app.post("/api/review-issues/{issue_id}/resolve")
async def resolve_issue(issue_id: str, body: dict) -> dict:
    try:
        return revision_store.resolve_issue(
            issue_id=issue_id,
            revision_id=str(body.get("revision_id", "")),
            expected_bundle_hash=str(body.get("expected_bundle_hash", "")),
            decision_kind=str(body.get("decision_kind", "accept_evidence")),
            rationale=str(body.get("rationale", "")),
            evidence_refs=list(body.get("evidence_refs", [])),
            idempotency_key=str(body.get("idempotency_key", "")),
            actor=str(body.get("actor", "reviewer")),
        )
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StaleCommandError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except IdempotencyConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/cases/{case_id}/officer-approval")
async def officer_approval(case_id: str, body: dict) -> dict:
    _ensure_revisions(case_id)
    try:
        binding = revision_store.approve(
            case_id=case_id,
            revision_id=str(body.get("revision_id", "")),
            package_hash=str(body.get("package_hash", "")),
            actor=str(body.get("actor", "officer")),
            role=str(body.get("role", "officer")),
            decision=body.get("decision", "approved"),
            reason=str(body.get("reason", "")),
        )
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StaleCommandError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return binding.model_dump(mode="json")


@app.get("/api/cases/{case_id}/snapshot")
async def case_snapshot(case_id: str) -> dict:
    _ensure_revisions(case_id)
    try:
        return revision_store.snapshot(case_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="covenant_agent",
        description="Evidence-grounded treasury copilot for covenant review.",
        graph=agent_graph,
    ),
    path="/ag-ui",
)
