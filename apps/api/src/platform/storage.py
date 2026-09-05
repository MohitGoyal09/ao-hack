"""Storage adapters for private covenant document bytes.

The service layer owns bytes; routes own HTTP. ``MemoryStorageAdapter`` is the
explicit offline/demo implementation. ``SupabaseStorageAdapter`` wraps a
Supabase client bound to the private ``covenant-private`` bucket.
"""

from __future__ import annotations

from typing import Any, Protocol


class StorageAdapter(Protocol):
    """Persistence contract for raw document bytes."""

    def upload(self, path: str, data: bytes, content_type: str) -> None: ...
    def download(self, path: str) -> bytes: ...


class MemoryStorageAdapter:
    """Dict-backed offline/demo implementation."""

    def __init__(self) -> None:
        self._blobs: dict[str, tuple[bytes, str]] = {}

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        self._blobs[path] = (bytes(data), content_type)

    def download(self, path: str) -> bytes:
        try:
            data, _ = self._blobs[path]
        except KeyError:
            raise FileNotFoundError(path) from None
        return data


class SupabaseStorageAdapter:
    """Supabase Storage implementation bound to one private bucket."""

    def __init__(self, client: Any, bucket: str = "covenant-private") -> None:
        self._client = client
        self._bucket = bucket

    def upload(self, path: str, data: bytes, content_type: str) -> None:
        self._client.storage.from_(self._bucket).upload(
            path=path,
            file=data,
            file_options={"content-type": content_type},
        )

    def download(self, path: str) -> bytes:
        return self._client.storage.from_(self._bucket).download(path)


def storage_adapter_from_env(
    client_or_none: Any | None,
    bucket: str = "covenant-private",
) -> StorageAdapter:
    """Return Supabase storage when a client is provided, else memory.

    An absent client is intentional offline/demo mode, never an error.
    """
    if client_or_none is not None:
        return SupabaseStorageAdapter(client_or_none, bucket)
    return MemoryStorageAdapter()
