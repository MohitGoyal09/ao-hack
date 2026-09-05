"""FastAPI and AG-UI adapters for Covenant Certificate."""

from __future__ import annotations

import asyncio
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
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.agent import build_agent_graph
from src.platform.jobqueue import (
    DurabilityComponentStatus,
    DurabilityConfigurationError,
    DurabilityRuntime,
    DurabilityStatus,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
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


if agent_graph is not None:
    add_langgraph_fastapi_endpoint(
        app=app,
        agent=LangGraphAGUIAgent(
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
