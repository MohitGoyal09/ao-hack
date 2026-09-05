"""Tamper-evident audit event construction."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .domain import AuditEvent
from .hashing import stable_hash


class AuditTrail:
    def __init__(self, created_at: datetime | None = None) -> None:
        self._created_at = created_at or datetime.now(UTC)
        self._events: list[AuditEvent] = []

    @property
    def created_at(self) -> datetime:
        return self._created_at

    def record(self, label: str, detail: str, artifact: Any) -> None:
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].artifact_hash if self._events else "GENESIS"
        event_hash = stable_hash(
            {
                "sequence": sequence,
                "previous_hash": previous_hash,
                "label": label,
                "detail": detail,
                "artifact": artifact,
            }
        )
        self._events.append(
            AuditEvent(
                sequence=sequence,
                step=str(sequence),
                label=label,
                detail=detail,
                artifact_hash=event_hash,
                created_at=self._created_at,
            )
        )

    def events(self) -> list[AuditEvent]:
        return list(self._events)
