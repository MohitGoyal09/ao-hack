"""Redacted Neatlogs instrumentation for workflow operations."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


class NeatlogsObserver:
    def __init__(self, enabled: bool, api_key: str, endpoint: str, workflow_name: str):
        self._enabled = enabled and bool(api_key)
        self._api_key = api_key
        self._endpoint = endpoint
        self._workflow_name = workflow_name
        self._sdk = None
        self._handler = None

    @classmethod
    def from_env(cls) -> "NeatlogsObserver":
        return cls(
            enabled=os.getenv("NEATLOGS_ENABLED", "false").lower() == "true",
            api_key=os.getenv("NEATLOGS_API_KEY", ""),
            endpoint=os.getenv("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com"),
            workflow_name=os.getenv(
                "NEATLOGS_WORKFLOW_NAME", "covenant-certificate"
            ),
        )

    @property
    def enabled(self) -> bool:
        return self._enabled and self._sdk is not None

    def initialize(self) -> None:
        if not self._enabled:
            return
        import neatlogs

        neatlogs.init(
            api_key=self._api_key,
            endpoint=self._endpoint,
            workflow_name=self._workflow_name,
            tags=["covenant-certificate", "fastapi", "langgraph"],
            capture_logs=False,
        )
        self._sdk = neatlogs
        self._handler = neatlogs.langchain_handler()

    def callbacks(self) -> list:
        return [self._handler] if self._handler is not None else []

    @contextmanager
    def workflow_span(self, case_id: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        # Only identifiers and status metadata leave the process. Contracts,
        # financial facts, tokens, and evidence excerpts are deliberately omitted.
        with self._sdk.trace("covenant_case_run"):
            self._sdk.log("processing covenant case {case_id}", case_id=case_id)
            yield

    def record_outcome(self, case_id: str, run_id: str, status: str) -> None:
        if self.enabled:
            self._sdk.log(
                "completed covenant run {run_id}",
                case_id=case_id,
                run_id=run_id,
                status=status,
            )

    def shutdown(self) -> None:
        if self.enabled:
            self._sdk.flush()
            self._sdk.shutdown()
