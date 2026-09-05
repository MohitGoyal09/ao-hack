"""Deep workflow module exposed to HTTP, AG-UI tools, and tests."""

from __future__ import annotations

from typing import Any

from .calculator import CovenantCalculator
from .certificate import CertificateRenderer
from .domain import CovenantCase, RunRequest, WorkflowResult
from .orchestration import CovenantOrchestrator
from .policy import ReviewPolicy
from .repository import InMemoryRepository


def case_summary(case: CovenantCase) -> dict[str, str]:
    return {
        "id": case.id,
        "name": case.name,
        "narrative": case.narrative,
        "agreement": case.agreement,
        "agreement_version": case.agreement_version,
        "test_date": case.test_date,
        "scenario_type": case.scenario_type,
        "covenant_name": case.rule.name,
    }


class CovenantWorkflow:
    """Small interface hiding the complete covenant decision implementation."""

    def __init__(
        self,
        repository: InMemoryRepository,
        calculator: CovenantCalculator | None = None,
        policy: ReviewPolicy | None = None,
        renderer: CertificateRenderer | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = CovenantOrchestrator(
            repository,
            calculator or CovenantCalculator(),
            policy or ReviewPolicy(),
            renderer or CertificateRenderer(),
        )

    @property
    def engine_name(self) -> str:
        return self._orchestrator.engine_name

    def list_cases(self) -> list[dict[str, str]]:
        return [case_summary(case) for case in self._repository.list_cases()]

    def describe(self, case_id: str) -> dict[str, str]:
        return case_summary(self._repository.get_case(case_id))

    def run(
        self,
        case_id: str,
        command: RunRequest | None = None,
        callbacks: list[Any] | None = None,
    ) -> WorkflowResult:
        return self._orchestrator.invoke(
            case_id, command or RunRequest(), callbacks=callbacks
        )

    def history(self, case_id: str) -> list[dict]:
        return [
            {
                "run_id": result.run_id,
                "status": result.status,
                "certificate_id": result.certificate.id,
                "generated_at": result.certificate.generated_at,
            }
            for result in self._repository.history(case_id)
        ]
