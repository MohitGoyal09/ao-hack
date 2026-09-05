"""LangGraph orchestration for the deterministic covenant workflow.

LangGraph owns state transitions and the human-review branch.  Domain decisions
remain in the calculator and review-policy modules, which keeps orchestration
observable without allowing the graph or an LLM to invent financial arithmetic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, NotRequired, TypedDict

from .audit import AuditTrail
from .calculator import CovenantCalculator
from .certificate import CertificateRenderer
from .domain import (
    CalculationResult,
    CovenantCase,
    DraftCertificate,
    DraftStatus,
    EvidenceItem,
    ReviewIssue,
    ReviewerDecision,
    RunRequest,
    WorkflowResult,
)
from .evidence import assemble_evidence
from .hashing import short_hash
from .policy import ReviewPolicy
from .repository import InMemoryRepository

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:  # Supports dependency-light domain tests.
    END = START = StateGraph = None  # type: ignore[assignment]


class WorkflowState(TypedDict):
    case_id: str
    command: RunRequest
    case: NotRequired[CovenantCase]
    created_at: NotRequired[datetime]
    audit: NotRequired[AuditTrail]
    calculation: NotRequired[CalculationResult]
    calculation_issues: NotRequired[list[ReviewIssue]]
    status: NotRequired[DraftStatus]
    status_reason: NotRequired[str]
    review_issues: NotRequired[list[ReviewIssue]]
    evidence: NotRequired[list[EvidenceItem]]
    certificate: NotRequired[DraftCertificate]
    result: NotRequired[WorkflowResult]


class CovenantOrchestrator:
    """Execute the workflow through LangGraph, with a test-only sequential fallback."""

    def __init__(
        self,
        repository: InMemoryRepository,
        calculator: CovenantCalculator,
        policy: ReviewPolicy,
        renderer: CertificateRenderer,
    ) -> None:
        self._repository = repository
        self._calculator = calculator
        self._policy = policy
        self._renderer = renderer
        self._graph = self._compile_graph() if StateGraph is not None else None

    @property
    def engine_name(self) -> str:
        return "langgraph" if self._graph is not None else "sequential-test-fallback"

    def invoke(
        self,
        case_id: str,
        command: RunRequest,
        callbacks: list[Any] | None = None,
    ) -> WorkflowResult:
        initial: WorkflowState = {"case_id": case_id, "command": command}
        if self._graph is not None:
            config = {"callbacks": callbacks or []}
            state = self._graph.invoke(initial, config=config)
        else:
            state = initial
            for node in (
                self._resolve_documents,
                self._compile_rule,
                self._map_evidence,
                self._calculate,
                self._apply_policy,
            ):
                state.update(node(state))
            if command.reviewer_decision != ReviewerDecision.PENDING:
                state.update(self._record_review(state))
            state.update(self._assemble_evidence(state))
            state.update(self._render_certificate(state))
            state.update(self._finalize(state))
        return state["result"]

    def _compile_graph(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("resolve_documents", self._resolve_documents)
        builder.add_node("compile_rule", self._compile_rule)
        builder.add_node("map_evidence", self._map_evidence)
        builder.add_node("calculate", self._calculate)
        builder.add_node("apply_policy", self._apply_policy)
        builder.add_node("record_review", self._record_review)
        builder.add_node("assemble_evidence", self._assemble_evidence)
        builder.add_node("render_certificate", self._render_certificate)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "resolve_documents")
        builder.add_edge("resolve_documents", "compile_rule")
        builder.add_edge("compile_rule", "map_evidence")
        builder.add_edge("map_evidence", "calculate")
        builder.add_edge("calculate", "apply_policy")
        builder.add_conditional_edges(
            "apply_policy",
            self._review_route,
            {
                "record_review": "record_review",
                "assemble_evidence": "assemble_evidence",
            },
        )
        builder.add_edge("record_review", "assemble_evidence")
        builder.add_edge("assemble_evidence", "render_certificate")
        builder.add_edge("render_certificate", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    @staticmethod
    def _review_route(state: WorkflowState) -> str:
        return (
            "record_review"
            if state["command"].reviewer_decision != ReviewerDecision.PENDING
            else "assemble_evidence"
        )

    def _resolve_documents(self, state: WorkflowState) -> dict:
        case = self._repository.get_case(state["case_id"])
        audit = AuditTrail(datetime.now(UTC))
        controlling = [document for document in case.documents if document.controlling]
        audit.record(
            "Resolved controlling agreement",
            controlling[0].title if len(controlling) == 1 else "Document precedence unresolved",
            case.documents,
        )
        return {"case": case, "audit": audit, "created_at": audit.created_at}

    @staticmethod
    def _compile_rule(state: WorkflowState) -> dict:
        case, audit = state["case"], state["audit"]
        audit.record("Compiled cited covenant rule", case.rule.name, case.rule)
        return {}

    @staticmethod
    def _map_evidence(state: WorkflowState) -> dict:
        case, audit = state["case"], state["audit"]
        audit.record(
            "Mapped financial evidence",
            f"{len(case.facts)} facts mapped for {case.rule.measurement_period}",
            case.facts,
        )
        return {}

    def _calculate(self, state: WorkflowState) -> dict:
        calculation, issues = self._calculator.calculate(
            state["case"], state["command"].reviewer_decision
        )
        ratio_text = (
            f"{calculation.ratio:.2f}x vs {calculation.threshold:.2f}x"
            if calculation.ratio is not None
            else "No decisionable ratio"
        )
        state["audit"].record("Calculated deterministically", ratio_text, calculation)
        return {"calculation": calculation, "calculation_issues": issues}

    def _apply_policy(self, state: WorkflowState) -> dict:
        status, reason, issues = self._policy.assess(
            state["case"],
            state["calculation"],
            state["command"],
            state["calculation_issues"],
        )
        state["audit"].record("Applied review policy", reason, issues)
        return {"status": status, "status_reason": reason, "review_issues": issues}

    @staticmethod
    def _record_review(state: WorkflowState) -> dict:
        command = state["command"]
        state["audit"].record(
            "Reviewer decision recorded",
            f"{command.reviewer_decision.value} by {command.reviewer_name or 'unnamed reviewer'}",
            command,
        )
        return {}

    @staticmethod
    def _assemble_evidence(state: WorkflowState) -> dict:
        evidence = assemble_evidence(state["case"], state["command"])
        state["audit"].record(
            "Assembled evidence manifest",
            f"{len(evidence)} linked evidence items",
            evidence,
        )
        return {"evidence": evidence}

    def _render_certificate(self, state: WorkflowState) -> dict:
        certificate = self._renderer.render(
            state["case"],
            state["status"],
            state["calculation"],
            state["evidence"],
            generated_at=state["created_at"],
        )
        state["audit"].record(
            "Prepared versioned draft certificate", certificate.id, certificate
        )
        return {"certificate": certificate}

    def _finalize(self, state: WorkflowState) -> dict:
        case = state["case"]
        run_identity = {
            "case": case.id,
            "command": state["command"],
            "certificate": state["certificate"].id,
            "created_at": state["created_at"],
        }
        result = WorkflowResult(
            run_id=f"run-{short_hash(run_identity)}",
            case={
                "id": case.id,
                "name": case.name,
                "narrative": case.narrative,
                "agreement": case.agreement,
                "agreement_version": case.agreement_version,
                "test_date": case.test_date,
                "scenario_type": case.scenario_type,
                "covenant_name": case.rule.name,
            },
            status=state["status"],
            status_reason=state["status_reason"],
            calculation=state["calculation"],
            citations=case.rule.citations,
            evidence=state["evidence"],
            blocking_issues=[
                issue.message
                for issue in state["review_issues"]
                if issue.severity == "blocking"
            ],
            review_issues=state["review_issues"],
            trace=state["audit"].events(),
            certificate=state["certificate"],
        )
        self._repository.save_run(result)
        return {"result": result}
