"""FastAPI and AG-UI adapters for Covenant Certificate."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Any

from dotenv import load_dotenv

load_dotenv()

# Neatlogs must initialize before LangGraph/provider imports.
from src.platform.observability import NeatlogsObserver

observer = NeatlogsObserver.from_env()
observer.initialize()

from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agent import build_agent_graph
from src.platform.jobqueue import (
    DurabilityComponentStatus,
    DurabilityConfigurationError,
    DurabilityRuntime,
    DurabilityStatus,
    JobConflictError,
    MemoryJobStore,
    build_durability_runtime,
)
from src.covenant import RunRequest, UnknownCaseError, build_demo_workflow
from src.covenant.revision_repository import (
    MemoryRevisionRepository,
    PostgresRevisionRepository,
    configured_database_url as revision_database_url,
    revision_repository_from_env,
)
from src.covenant.revisions import (
    IdempotencyConflictError,
    StaleCommandError,
    UnknownRevisionError,
)
from src.platform.supabase import (
    AuthenticationError,
    PersistenceError,
    Principal,
    SupabasePlatform,
)

workflow = build_demo_workflow()
platform = SupabasePlatform.from_env()
default_durability_runtime = build_durability_runtime()

# Revision persistence: Postgres when DATABASE_URL is configured, explicit
# memory otherwise. A configured but unusable database never downgrades to
# memory; it marks readiness unready instead.
revision_repository: (
    MemoryRevisionRepository | PostgresRevisionRepository | None
)
try:
    revision_repository = revision_repository_from_env()
except DurabilityConfigurationError:
    revision_repository = None

if revision_repository is None:
    _revision_component = DurabilityComponentStatus.failed("revisions")
elif isinstance(revision_repository, PostgresRevisionRepository):
    _revision_component = DurabilityComponentStatus(
        component="revisions", configured=True, verified=True, mode="postgres"
    )
else:
    _revision_component = DurabilityComponentStatus.offline("revisions")

_revision_component_value: DurabilityComponentStatus = _revision_component

combined_durability_status = DurabilityStatus(
    queue=default_durability_runtime.status.queue,
    checkpoint=default_durability_runtime.status.checkpoint,
    revisions=_revision_component_value,
)

# Backwards-compatible alias for tests and tooling.
revision_store = revision_repository

# Document intake singletons (sibling-owned contract; guarded so the app and
# existing routes stay up when the sibling branch has not landed yet).
try:
    from src.platform.storage import storage_adapter_from_env
    from src.covenant.documents import (
        ALLOWED_ROLES,
        MAX_BYTES,
        DocumentService,
        UnknownDocumentError,
    )

    _intake_contract_error: Exception | None = None
except Exception as _intake_import_error:  # sibling files not present yet
    storage_adapter_from_env = None  # type: ignore[assignment]
    DocumentService = None  # type: ignore[assignment]
    UnknownDocumentError = None  # type: ignore[assignment]
    ALLOWED_ROLES = None  # type: ignore[assignment]
    MAX_BYTES = None  # type: ignore[assignment]
    _intake_contract_error = _intake_import_error


def _platform_storage_client():
    """Getattr-safe accessor; None when the platform is in offline demo mode."""
    try:
        if getattr(platform, "enabled", False):
            return getattr(platform, "_client", None)
    except Exception:
        return None
    return None


if DocumentService is not None and storage_adapter_from_env is not None:
    _storage = storage_adapter_from_env(_platform_storage_client())
    _documents = DocumentService(revision_database_url(), _storage)
else:
    _storage = None
    _documents = None

agent_graph = (
    build_agent_graph(workflow, checkpointer=default_durability_runtime.checkpointer)
    if default_durability_runtime.status.ready
    else None
)

REVIEWER_ROLES = frozenset({"treasury_reviewer", "officer", "admin"})
OFFICER_ROLES = frozenset({"officer", "admin"})
KNOWN_ROLES = frozenset({"viewer", "treasury_reviewer", "officer", "admin"})


def _parse_offline_principal(authorization: str) -> Principal:
    """Parse an offline demo credential of the form ``user:role[:org]``.

    Offline mode has no Supabase session to verify, so tests and local demos
    carry explicit identity in the bearer token. Missing or malformed
    credentials are rejected; callers must supply identity on every private
    revision route.
    """
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication is required")
    parts = token.split(":")
    user_id = parts[0].strip() or "demo-user"
    role = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "treasury_reviewer"
    if role not in KNOWN_ROLES:
        raise HTTPException(status_code=401, detail="Unknown role in credential")
    return Principal(user_id, None, role)


def _offline_org(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        return "demo-org"
    parts = authorization.removeprefix("Bearer ").strip().split(":")
    if len(parts) > 2 and parts[2].strip():
        return parts[2].strip()
    return "demo-org"


async def require_revision_principal(
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Strict identity for private revision routes: never trust body fields."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication is required")
    if platform.enabled:
        try:
            return await asyncio.to_thread(platform.authenticate, authorization)
        except AuthenticationError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
    return _parse_offline_principal(authorization)


def _active_revision_repository():
    if revision_repository is None:
        raise HTTPException(
            status_code=503, detail="Revision persistence is unavailable"
        )
    return revision_repository


def _offline_member_role(repo: Any, org_id: str, principal: Principal,
                         authorization: str | None) -> str | None:
    """Offline demo membership: auto-provision same-org users, block others.

    The bearer token carries an organization claim. A token for another org
    never gains membership (callers turn None into 404); a new user of the
    same org is seeded with its token role so reviewer/officer demo flows
    work without a signup API.
    """
    if revision_database_url() is not None:
        return repo.get_member_role(org_id, principal.user_id)
    if authorization is not None and _offline_org(authorization) != org_id:
        return None
    existing = repo.get_member_role(org_id, principal.user_id)
    if existing is None and isinstance(repo, MemoryRevisionRepository):
        repo.seed_member(org_id, principal.user_id, principal.role)
        return principal.role
    return existing


def _require_case_member(case_id: str, principal: Principal,
                         authorization: str | None) -> tuple[Any, str]:
    """Ensure the principal belongs to the case organization.

    Unknown cases and foreign-tenant cases both return 404 so the existence
    of another tenant's records never leaks. Returns (repo, org_id).
    """
    repo = _active_revision_repository()
    try:
        org_id = repo.get_case_org(case_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail="Unknown covenant case") from error
    role = _offline_member_role(repo, org_id, principal, authorization)
    if role is None:
        raise HTTPException(status_code=404, detail="Unknown covenant case")
    return repo, org_id


def _ensure_revisions(case_id: str, principal: Principal,
                      authorization: str | None) -> str:
    """Seed revision state for a demo-workflow case under the caller's org.

    Returns the organization ID the case belongs to. New cases are created
    under the caller's organization; existing cases keep theirs and foreign
    callers receive 404 via the membership check below.
    """
    repo = _active_revision_repository()
    try:
        org_id = repo.get_case_org(case_id)
    except UnknownRevisionError:
        org_id = None
    if org_id is None:
        try:
            case = workflow._repository.get_case(case_id)  # noqa: SLF001
        except UnknownCaseError:
            raise HTTPException(status_code=404, detail="Unknown covenant case")
        if revision_database_url() is not None:
            orgs = repo.member_orgs(principal.user_id)
            if not orgs:
                raise HTTPException(status_code=404, detail="Unknown covenant case")
            org_id = orgs[0][0]
        else:
            assert authorization is not None
            org_id = _offline_org(authorization)
            existing_role = repo.get_member_role(org_id, principal.user_id)
            if existing_role is None and isinstance(repo, MemoryRevisionRepository):
                repo.seed_member(org_id, principal.user_id, principal.role)
        repo.ensure_case(
            case_id=case.id, organization_id=org_id, user_id=principal.user_id,
            test_date=case.test_date, rule_id=case.rule.id,
            threshold=case.rule.threshold,
            doc_ids=[d.id for d in case.documents],
            fact_keys=[f.key for f in case.facts],
        )
    else:
        role = _offline_member_role(repo, org_id, principal, authorization)
        if role is None:
            raise HTTPException(status_code=404, detail="Unknown covenant case")
    assert org_id is not None
    return org_id


def _start_inprocess_worker(app: FastAPI) -> threading.Event | None:
    """Offline demo only: drain the MemoryJobStore from a daemon thread.

    Without a database there is no separate worker process, so uploads would
    sit at ``queued`` forever. INPROCESS_WORKER=0 disables it (tests that
    assert ``queued`` run without lifespan anyway). Postgres mode never runs
    this: the real worker is ``python -m src.platform.worker``.
    """
    store = getattr(getattr(app.state, "durability_runtime", None), "job_store", None)
    if (os.getenv("INPROCESS_WORKER", "1") != "1"
            or type(store) is not MemoryJobStore or _documents is None):
        return None
    from src.covenant.pipeline import CasePipeline
    from src.platform.worker import Worker

    # Share the route's memory revision repo (RUN_* events, run_state and
    # artifacts show in the snapshot) and its in-memory document index.
    pipeline = CasePipeline(
        None, _storage,
        revision_repository=revision_repository
        if isinstance(revision_repository, MemoryRevisionRepository) else None,
    )
    # ponytail: documents shared by attribute; add a ctor kwarg if a third caller appears.
    pipeline.documents = _documents
    stop = threading.Event()
    threading.Thread(
        target=Worker(store, pipeline, worker_id="inprocess").run_forever,
        kwargs={"poll_interval_seconds": 0.5, "stop_event": stop},
        name="inprocess-worker",
        daemon=True,
    ).start()
    return stop


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_worker = _start_inprocess_worker(app)
    yield
    if stop_worker is not None:
        stop_worker.set()
    runtime = getattr(app.state, "durability_runtime", None)
    if runtime is not None:
        runtime.close()
    observer.shutdown()


app = FastAPI(
    title="Covenant Certificate API",
    version="0.2.0",
    description="Evidence-first covenant workflow with LangGraph and AG-UI.",
    lifespan=lifespan,
)
app.state.durability_runtime = default_durability_runtime
app.state.durability_status = combined_durability_status
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
async def health(request: Request) -> dict:
    return {
        "status": "ok",
        "service": "covenant-certificate",
        "orchestrator": workflow.engine_name,
        "supabase": "configured" if platform.enabled else "offline-demo",
        "neatlogs": "configured" if observer.enabled else "disabled",
        "agent_transport": "ag-ui",
        "durability": request.app.state.durability_status.public_dict(),
    }


@app.get("/health/live")
async def liveness() -> dict:
    """Process liveness; it remains available during dependency outages."""
    return {"status": "live", "service": "covenant-certificate"}


@app.get("/health/ready")
async def readiness(request: Request):
    """Readiness distinguishes intentional offline demo mode from an outage."""
    status: DurabilityStatus = request.app.state.durability_status
    if not status.ready:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unready",
                "durability": status.public_dict(),
            },
        )
    if status.degraded:
        return {
            "status": "ready",
            "durability": {**status.public_dict(), "mode": "offline-memory", "status": "degraded"},
        }
    return {"status": "ready", "durability": {**status.public_dict(), "mode": "postgres", "status": "ready"}}


@app.middleware("http")
async def reject_business_traffic_when_unready(request, call_next):
    if not request.app.state.durability_status.ready and request.url.path not in {
        "/health",
        "/health/live",
        "/health/ready",
    }:
        return JSONResponse(
            status_code=503, content={"detail": "Service durability is unavailable"}
        )
    return await call_next(request)


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
async def create_revision(
    case_id: str,
    body: dict,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> dict:
    repo = _active_revision_repository()
    authorization = request.headers.get("authorization")
    org_id = _ensure_revisions(case_id, principal, authorization)
    _require_case_member(case_id, principal, authorization)
    try:
        rev, changeset, impact = repo.create_revision(
            case_id=case_id,
            organization_id=org_id,
            user_id=principal.user_id,
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
async def revision_impact(
    case_id: str,
    revision_id: str,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> dict:
    repo = _active_revision_repository()
    authorization = request.headers.get("authorization")
    _ensure_revisions(case_id, principal, authorization)
    _require_case_member(case_id, principal, authorization)
    try:
        rev = repo.get(case_id, revision_id)
        impact = repo.impact(case_id, revision_id)
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
async def resolve_issue(
    issue_id: str,
    body: dict,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> dict:
    repo = _active_revision_repository()
    authorization = request.headers.get("authorization")
    try:
        case_id, org_id, _ = repo.get_issue_case(issue_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    role = _offline_member_role(repo, org_id, principal, authorization)
    if role is None:
        raise HTTPException(status_code=404, detail="Unknown review issue")
    if role not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient role")
    try:
        return repo.resolve_issue(
            issue_id=issue_id,
            organization_id=org_id,
            user_id=principal.user_id,
            role=role,
            revision_id=str(body.get("revision_id", "")),
            expected_bundle_hash=str(body.get("expected_bundle_hash", "")),
            decision_kind=str(body.get("decision_kind", "accept_evidence")),
            rationale=str(body.get("rationale", "")),
            evidence_refs=list(body.get("evidence_refs", [])),
            idempotency_key=str(body.get("idempotency_key", "")),
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
async def officer_approval(
    case_id: str,
    body: dict,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> dict:
    repo = _active_revision_repository()
    authorization = request.headers.get("authorization")
    org_id = _ensure_revisions(case_id, principal, authorization)
    _require_case_member(case_id, principal, authorization)
    role = repo.get_member_role(org_id, principal.user_id)
    if role not in OFFICER_ROLES:
        raise HTTPException(status_code=403, detail="Officer role is required")
    try:
        case = workflow._repository.get_case(case_id)  # noqa: SLF001
    except UnknownCaseError as error:
        raise HTTPException(status_code=404, detail="Unknown covenant case") from error
    from src.covenant.calculator import CovenantCalculator
    from src.covenant.domain import ReviewerDecision, money_str

    revision_id = str(body.get("revision_id", ""))
    try:
        head = repo.get(case_id, revision_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    rule = case.rule.model_copy(update={"threshold": float(head.threshold)})
    calculation, _ = CovenantCalculator().calculate(case.model_copy(update={"rule": rule}), ReviewerDecision.PENDING)
    fresh_inputs = {line.fact_key: money_str(line.amount) for line in calculation.lines if line.included}
    try:
        binding = repo.approve(
            case_id=case_id,
            organization_id=org_id,
            user_id=principal.user_id,
            role=role,
            revision_id=revision_id,
            package_hash=str(body.get("package_hash", "")),
            decision=body.get("decision", "approved"),
            reason=str(body.get("reason", "")),
            approved_ratio=body.get("approved_ratio"),
            approved_threshold=body.get("approved_threshold"),
            approved_comparator=body.get("approved_comparator"),
            approved_inputs=body.get("approved_inputs"),
            fresh_ratio=None if calculation.ratio is None else money_str(calculation.ratio),
            fresh_threshold=money_str(calculation.threshold),
            fresh_comparator=calculation.comparator,
            fresh_inputs=fresh_inputs,
        )
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StaleCommandError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    payload = binding.model_dump(mode="json")
    payload["locked_summary"] = binding.locked_summary()
    return payload


@app.get("/api/cases/{case_id}/snapshot")
async def case_snapshot(
    case_id: str,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> dict:
    repo = _active_revision_repository()
    authorization = request.headers.get("authorization")
    _ensure_revisions(case_id, principal, authorization)
    _require_case_member(case_id, principal, authorization)
    try:
        return repo.snapshot(case_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _parse_document_location(loc: Any) -> tuple[str | None, str | None, dict | None]:
    """Best-effort (case_id, organization_id, metadata) from find_location()."""
    if loc is None:
        return None, None, None
    if isinstance(loc, (tuple, list)) and len(loc) >= 2:
        meta = None
        if len(loc) >= 3 and isinstance(loc[2], dict):
            meta = loc[2]
        return str(loc[0]), str(loc[1]), meta
    if isinstance(loc, dict):
        case_id = loc.get("case_id") or loc.get("caseId")
        org_id = (
            loc.get("organization_id") or loc.get("org_id")
            or loc.get("organizationId") or loc.get("org")
        )
        meta = dict(loc) if case_id is not None or org_id is not None else None
        return (
            str(case_id) if case_id is not None else None,
            str(org_id) if org_id is not None else None,
            meta,
        )
    case_id = getattr(loc, "case_id", None) or getattr(loc, "caseId", None)
    org_id = (
        getattr(loc, "organization_id", None) or getattr(loc, "org_id", None)
        or getattr(loc, "organizationId", None) or getattr(loc, "org", None)
    )
    meta = None
    to_dict = getattr(loc, "model_dump", None) or getattr(loc, "dict", None)
    if callable(to_dict):
        try:
            dumped = to_dict(mode="json") if "mode" in str(to_dict) else to_dict()
            if isinstance(dumped, dict):
                meta = dumped
        except Exception:
            meta = None
    return (
        str(case_id) if case_id is not None else None,
        str(org_id) if org_id is not None else None,
        meta,
    )


@app.post("/api/cases/{case_id}/documents")
async def upload_case_document(
    case_id: str,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
    file: UploadFile = File(...),
    document_role: str = Form(...),
    title: str = Form(...),
    document_id: str | None = Form(None),
    effective_date: str | None = Form(None),
    period_start: str | None = Form(None),
    period_end: str | None = Form(None),
) -> dict:
    """Store covenant evidence, then version it as exactly one revision+job."""
    if _documents is None or MAX_BYTES is None:
        raise HTTPException(status_code=503, detail="Document intake is unavailable")
    repo = _active_revision_repository()
    authorization = request.headers.get("authorization")
    org_id = _ensure_revisions(case_id, principal, authorization)
    _require_case_member(case_id, principal, authorization)
    role = _offline_member_role(repo, org_id, principal, authorization)
    if role is None:
        raise HTTPException(status_code=404, detail="Unknown covenant case")
    if role not in REVIEWER_ROLES:
        raise HTTPException(status_code=403, detail="Insufficient role")
    data = bytearray()
    while True:
        chunk = await file.read(1 << 20)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > int(MAX_BYTES):
            raise HTTPException(status_code=413, detail="Uploaded file exceeds size limit")
    content = bytes(data)
    filename = file.filename or "upload"
    content_type = file.content_type or "application/octet-stream"
    try:
        version = _documents.upload(
            organization_id=org_id,
            user_id=principal.user_id,
            case_id=case_id,
            filename=filename,
            content_type=content_type,
            data=content,
            document_role=document_role,
            title=title,
            document_id=document_id,
            effective_date=effective_date,
            period_start=period_start,
            period_end=period_end,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Unknown document") from error
    try:
        head = repo.current(case_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail="Unknown covenant case") from error
    try:
        new_rev, _, _ = repo.create_revision(
            case_id=case_id,
            organization_id=org_id,
            user_id=principal.user_id,
            expected_parent=head.revision_id,
            change_kind="document_upload",
            documents=[version.document_id],
            facts=[],
        )
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except StaleCommandError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    repo.append_event(
        case_id,
        org_id,
        new_rev.revision_id,
        None,
        "DOCUMENT_UPLOADED",
        {"document_id": version.document_id, "version": version.version_number},
    )
    job_store = request.app.state.durability_runtime.job_store
    try:
        job = job_store.enqueue(
            case_id,
            new_rev.revision_id,
            {"document_id": version.document_id, "version": version.version_number},
        )
    except JobConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "document_id": version.document_id,
        "version_id": version.id,
        "version_number": version.version_number,
        "sha256": version.sha256,
        "extraction_state": version.extraction_state,
        "revision_id": new_rev.revision_id,
        "job_id": job.id,
    }


@app.get("/api/documents/{document_id}")
async def get_document(
    document_id: str,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> dict:
    """Return stored-document metadata; never raw file bytes."""
    if _documents is None:
        raise HTTPException(status_code=503, detail="Document intake is unavailable")
    authorization = request.headers.get("authorization")
    repo = _active_revision_repository()
    find_location = getattr(_documents, "find_location", None)
    if find_location is None:
        raise HTTPException(status_code=503, detail="Document lookup is unavailable")
    try:
        loc = find_location(document_id)
    except Exception as error:
        if UnknownDocumentError is not None and isinstance(error, UnknownDocumentError):
            raise HTTPException(status_code=404, detail="Unknown document") from error
        if isinstance(error, LookupError):
            raise HTTPException(status_code=404, detail="Unknown document") from error
        raise
    case_id, org_id, meta = _parse_document_location(loc)
    if not case_id or not org_id:
        raise HTTPException(status_code=404, detail="Unknown document")
    role = _offline_member_role(repo, org_id, principal, authorization)
    if role is None:
        raise HTTPException(status_code=404, detail="Unknown document")
    if meta is not None:
        metadata: dict = {
            k: v for k, v in dict(meta).items()
            if k not in ("data", "bytes", "content", "file_bytes")
        }
        metadata.setdefault("document_id", document_id)
        metadata.setdefault("case_id", case_id)
        metadata.setdefault("organization_id", org_id)
        return metadata
    for method_name in ("describe", "get_metadata", "metadata", "get", "info"):
        method = getattr(_documents, method_name, None)
        if method is None:
            continue
        for args in (((document_id, org_id),), ((document_id,),)):
            try:
                candidate = method(*args[0])
            except TypeError:
                continue
            except Exception as error:
                if UnknownDocumentError is not None and isinstance(
                    error, UnknownDocumentError
                ):
                    raise HTTPException(
                        status_code=404, detail="Unknown document"
                    ) from error
                if isinstance(error, LookupError):
                    raise HTTPException(
                        status_code=404, detail="Unknown document"
                    ) from error
                raise
            if isinstance(candidate, dict):
                cleaned = {
                    k: v for k, v in candidate.items()
                    if k not in ("data", "bytes", "content", "file_bytes")
                }
                cleaned.setdefault("document_id", document_id)
                cleaned.setdefault("case_id", case_id)
                cleaned.setdefault("organization_id", org_id)
                return cleaned
            to_dict = getattr(candidate, "model_dump", None) or getattr(
                candidate, "dict", None
            )
            if callable(to_dict):
                try:
                    dumped = to_dict(mode="json")
                except Exception:
                    continue
                if isinstance(dumped, dict):
                    dumped.setdefault("document_id", document_id)
                    dumped.setdefault("case_id", case_id)
                    dumped.setdefault("organization_id", org_id)
                    return dumped
    return {
        "document_id": document_id,
        "case_id": case_id,
        "organization_id": org_id,
    }


# --- Job list/cancel routes (additive; existing routes/helpers untouched). ---

_TERMINAL_JOB_STATES = frozenset({"completed", "failed", "cancelled"})


def _serialize_job_summary(job: Any) -> dict:
    """Public job summary; never leaks payload bytes or auth secrets."""
    return {
        "job_id": job.id,
        "revision_id": job.revision_id,
        "state": job.state,
        "attempt_count": job.attempt_count,
        "fencing_token": job.fencing_token,
        "lease_owner": job.lease_owner,
        "last_error": job.last_error,
    }


def _jobs_for_case(job_store: Any, case_id: str) -> list[Any]:
    """Newest-first jobs for one case, capped at 50. Read-only."""
    try:
        from src.platform.jobqueue import PostgresJobStore
    except Exception:
        PostgresJobStore = None  # type: ignore[assignment]
    if PostgresJobStore is not None and isinstance(job_store, PostgresJobStore):
        with job_store._conn().cursor() as cur:  # noqa: SLF001
            cur.execute(
                f"select {job_store._COLS} from public.revision_run_jobs"  # noqa: SLF001
                " where case_id = %s order by created_at desc limit 50",
                (case_id,),
            )
            return [job_store._row_to_job(row) for row in cur.fetchall()]  # noqa: SLF001
    with job_store._lock:  # noqa: SLF001
        jobs = [j for j in list(job_store._jobs.values())  # noqa: SLF001
                if j.case_id == case_id]
    # MemoryJobStore carries no timestamps; dict insertion order is
    # oldest-first, so reversed order is newest-first.
    jobs.reverse()
    return jobs[:50]


@app.get("/api/cases/{case_id}/jobs")
async def list_case_jobs(
    case_id: str,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> list[dict]:
    authorization = request.headers.get("authorization")
    _ensure_revisions(case_id, principal, authorization)
    _require_case_member(case_id, principal, authorization)
    job_store = request.app.state.durability_runtime.job_store
    return [_serialize_job_summary(job) for job in _jobs_for_case(job_store, case_id)]


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    request: Request,
    principal: Principal = Depends(require_revision_principal),
) -> dict:
    repo = _active_revision_repository()
    authorization = request.headers.get("authorization")
    job_store = request.app.state.durability_runtime.job_store
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    try:
        org_id = repo.get_case_org(job.case_id)
    except UnknownRevisionError as error:
        raise HTTPException(status_code=404, detail="Unknown job") from error
    role = _offline_member_role(repo, org_id, principal, authorization)
    if role is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    # Cancellation is an explicit operator command, so any member role may
    # cancel; terminal jobs report their current state idempotently instead
    # of being transitioned (cancel must never revive a completed job).
    if job.state in _TERMINAL_JOB_STATES:
        return {"job_id": job.id, "state": job.state}
    try:
        cancelled = job_store.cancel(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Unknown job") from error
    return {"job_id": cancelled.id, "state": cancelled.state}


class CovenantAGUIAgent(LangGraphAGUIAgent):
    """ag-ui-langgraph 0.0.43 ``clone()`` forwards kwargs copilotkit 0.1.96's
    ``__init__`` does not accept (``enable_legacy_on_interrupt_event`` ...), so
    every ``POST /ag-ui`` 500s. Clone with the four kwargs the subclass takes."""

    def clone(self):
        return type(self)(
            name=self.name,
            graph=self.graph,
            description=self.description,
            config=dict(self.config) if self.config else None,
        )


if agent_graph is not None:
    add_langgraph_fastapi_endpoint(
        app=app,
        agent=CovenantAGUIAgent(
            name="covenant_agent",
            description="Evidence-grounded treasury copilot for covenant review.",
            graph=agent_graph,
        ),
        path="/ag-ui",
    )


def create_app(
    *,
    durability_status: DurabilityStatus | None = None,
    durability_runtime: DurabilityRuntime | None = None,
) -> FastAPI:
    """Create an HTTP app with an injected public durability seam for tests.

    Production uses the module's application-owned runtime. Test callers can
    provide a typed status without changing module globals or touching a real
    database.
    """
    if durability_status is None and durability_runtime is None:
        return app
    injected_status = durability_status or durability_runtime.status
    created = FastAPI(
        title=app.title,
        version=app.version,
        description=app.description,
        lifespan=lifespan,
    )
    created.state.durability_status = injected_status
    created.state.durability_runtime = durability_runtime
    created.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["authorization", "content-type"],
    )
    created.middleware("http")(reject_business_traffic_when_unready)
    created.router.routes.extend(app.router.routes)
    return created
