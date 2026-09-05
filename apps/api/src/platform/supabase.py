"""Supabase Auth, Postgres, and private Storage adapter.

The adapter is disabled when credentials are absent so curated demo cases remain
runnable offline. When configured, bearer authentication and durable persistence
are mandatory; persistence errors are surfaced rather than silently discarded.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from src.covenant import WorkflowResult


class AuthenticationError(PermissionError):
    pass


class PersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    user_id: str
    email: str | None
    role: str


class SupabasePlatform:
    def __init__(self, client: Any | None, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_env(cls) -> "SupabasePlatform":
        url = os.getenv("SUPABASE_URL", "").strip()
        key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
        bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "covenant-private").strip()
        if not url or not key:
            return cls(client=None, bucket=bucket)
        from supabase import create_client

        return cls(client=create_client(url, key), bucket=bucket)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def authenticate(self, authorization: str | None) -> Principal:
        if not self.enabled:
            return Principal("demo-user", "demo@local.invalid", "treasury_reviewer")
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthenticationError("A Supabase bearer token is required")
        token = authorization.removeprefix("Bearer ").strip()
        if not token:
            raise AuthenticationError("A Supabase bearer token is required")
        try:
            response = self._client.auth.get_user(token)
            user = response.user
        except Exception as error:
            raise AuthenticationError("The Supabase session is invalid") from error
        if not user:
            raise AuthenticationError("The Supabase session is invalid")
        metadata = user.app_metadata or {}
        role = metadata.get("role", "viewer")
        return Principal(str(user.id), getattr(user, "email", None), str(role))

    def persist_run(self, result: WorkflowResult, principal: Principal) -> str | None:
        if not self.enabled:
            return None
        payload = result.model_dump(mode="json")
        object_path = f"{principal.user_id}/{result.case['id']}/{result.run_id}.json"
        try:
            self._client.table("covenant_runs").insert(
                {
                    "id": result.run_id,
                    "owner_id": principal.user_id,
                    "case_id": result.case["id"],
                    "status": result.status.value,
                    "result": payload,
                    "certificate_id": result.certificate.id,
                    "artifact_path": object_path,
                }
            ).execute()
            self._client.storage.from_(self._bucket).upload(
                path=object_path,
                file=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
                file_options={"content-type": "application/json", "upsert": "false"},
            )
        except Exception as error:
            raise PersistenceError("Supabase could not persist the workflow run") from error
        return object_path

    def signed_artifact_url(
        self, object_path: str, expires_in_seconds: int = 300
    ) -> str | None:
        if not self.enabled:
            return None
        try:
            response = (
                self._client.storage.from_(self._bucket)
                .create_signed_url(object_path, expires_in_seconds)
            )
            return response.get("signedURL") or response.get("signedUrl")
        except Exception as error:
            raise PersistenceError("Supabase could not sign the artifact URL") from error
