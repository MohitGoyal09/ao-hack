"""Case and run storage adapters used by the standalone demo."""

from __future__ import annotations

from threading import RLock
from typing import Callable

from .domain import CovenantCase, WorkflowResult


class UnknownCaseError(LookupError):
    pass


class InMemoryRepository:
    """Thread-safe demo adapter; production replaces it with persisted storage."""

    def __init__(self, cases: dict[str, CovenantCase]) -> None:
        self._cases = cases
        self._runs: dict[str, list[WorkflowResult]] = {}
        self._lock = RLock()
        # Cases created from a template (POST /api/cases) are not curated:
        # ``resolve_derived(case_id)`` (bound by main.py to the revision
        # repository) returns {"template_case_id", "name", "test_date"} or
        # None, and the derived case is cached here, never in list_cases().
        self.resolve_derived: Callable[[str], dict | None] | None = None
        self._derived: dict[str, CovenantCase] = {}

    def list_cases(self) -> list[CovenantCase]:
        return list(self._cases.values())

    def get_case(self, case_id: str) -> CovenantCase:
        case = self._cases.get(case_id) or self._derived.get(case_id)
        if case is not None:
            return case
        info = self.resolve_derived(case_id) if self.resolve_derived else None
        template = self._cases.get((info or {}).get("template_case_id") or "")
        if template is None:
            raise UnknownCaseError(case_id)
        case = template.model_copy(deep=True, update={
            "id": case_id, "name": info.get("name") or template.name,
            "test_date": info.get("test_date") or template.test_date})
        self._derived[case_id] = case
        return case

    def save_run(self, result: WorkflowResult) -> None:
        with self._lock:
            self._runs.setdefault(result.case["id"], []).append(result)

    def history(self, case_id: str) -> list[WorkflowResult]:
        self.get_case(case_id)
        with self._lock:
            return list(self._runs.get(case_id, []))
