"""Public interface for Covenant Certificate's backend workflow."""

from .catalog import build_demo_catalog
from .domain import DraftStatus, ReviewerDecision, RunRequest, WorkflowResult
from .repository import InMemoryRepository, UnknownCaseError
from .workflow import CovenantWorkflow


def build_demo_workflow() -> CovenantWorkflow:
    return CovenantWorkflow(InMemoryRepository(build_demo_catalog()))


__all__ = [
    "CovenantWorkflow",
    "DraftStatus",
    "ReviewerDecision",
    "RunRequest",
    "UnknownCaseError",
    "WorkflowResult",
    "build_demo_workflow",
]
