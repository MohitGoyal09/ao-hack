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
from src.platform.supabase import (
    AuthenticationError,
    PersistenceError,
    Principal,
    SupabasePlatform,
)

workflow = build_demo_workflow()
platform = SupabasePlatform.from_env()
agent_graph = build_agent_graph(workflow)


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


add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="covenant_agent",
        description="Evidence-grounded treasury copilot for covenant review.",
        graph=agent_graph,
    ),
    path="/ag-ui",
)
