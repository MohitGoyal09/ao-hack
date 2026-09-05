"""Case and run storage adapters used by the standalone demo."""

from __future__ import annotations

from threading import RLock

from .domain import CovenantCase, WorkflowResult


class UnknownCaseError(LookupError):
    pass


class InMemoryRepository:
    """Thread-safe demo adapter; production replaces it with persisted storage."""

    def __init__(self, cases: dict[str, CovenantCase]) -> None:
        self._cases = cases
        self._runs: dict[str, list[WorkflowResult]] = {}
        self._lock = RLock()

    def list_cases(self) -> list[CovenantCase]:
        return list(self._cases.values())

    def get_case(self, case_id: str) -> CovenantCase:
        try:
            return self._cases[case_id]
        except KeyError as error:
            raise UnknownCaseError(case_id) from error

    def save_run(self, result: WorkflowResult) -> None:
        with self._lock:
            self._runs.setdefault(result.case["id"], []).append(result)

    def history(self, case_id: str) -> list[WorkflowResult]:
        self.get_case(case_id)
        with self._lock:
            return list(self._runs.get(case_id, []))
