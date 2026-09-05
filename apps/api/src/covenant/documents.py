"""Document intake service: validated uploads with version history.

Service-level rules only; routes own HTTP mapping. Money is not involved
here. File bytes are never logged, only hashes, sizes, and paths.
"""

from __future__ import annotations

import hashlib
import io
import os
import uuid
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from src.platform.storage import StorageAdapter

ALLOWED_ROLES = frozenset({
    "credit_agreement",
    "amendment",
    "financial_statement",
    "supporting_evidence",
    "certificate_form",
})

ALLOWED_MEDIA = frozenset({
    "application/pdf",
    "application/json",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
})

MAX_BYTES = 50 * 1024 * 1024

STORAGE_BUCKET = "covenant-private"


class UnknownDocumentError(LookupError):
    """Unknown document id, or a document from another organization.

    The same error covers both cases so the existence of another tenant's
    records never leaks.
    """


def _require_uuid(value: str) -> str:
    """Validate a document id as UUID; malformed ids are unknown, not 500s."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise UnknownDocumentError(value) from None


class DocumentRecord(BaseModel):
    id: str
    organization_id: str
    case_id: str
    document_role: str
    title: str


class DocumentVersionRecord(BaseModel):
    id: str
    document_id: str
    organization_id: str
    version_number: int
    storage_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_size: int
    media_type: str
    extraction_state: str
    title: str


def classify_upload(media_type: str, data: bytes) -> str:
    """Initial extraction state for an accepted upload."""
    if media_type in (
        "text/csv",
        "application/json",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ):
        return "pending"
    if media_type == "application/pdf":
        try:
            import pdfplumber

            with pdfplumber.open(io.BytesIO(data)) as pdf:
                for page in pdf.pages[:3]:
                    if (page.extract_text() or "").strip():
                        return "pending"
        except Exception:
            return "needs_ocr"
        return "needs_ocr"
    return "unsupported"


def _normalize_filename(filename: str) -> str:
    stripped = (filename or "").strip()
    if not stripped:
        raise ValueError("filename is required")
    segments = stripped.replace("\\", "/").split("/")
    if any(segment == ".." for segment in segments):
        raise ValueError("invalid filename: path traversal is not allowed")
    base = os.path.basename(stripped.replace("\\", "/")).strip()
    if not base or base in (".", ".."):
        raise ValueError("invalid filename")
    if "/" in base or "\\" in base or "\x00" in base:
        raise ValueError("invalid filename")
    return base


def _validate_upload(
    *,
    organization_id: str,
    user_id: str,
    case_id: str,
    filename: str,
    content_type: str,
    data: bytes,
    document_role: str,
    title: str,
    effective_date: str | None,
    period_start: str | None,
    period_end: str | None,
) -> str:
    if not (organization_id or "").strip():
        raise ValueError("organization_id is required")
    if not (user_id or "").strip():
        raise ValueError("user_id is required")
    if not (case_id or "").strip():
        raise ValueError("case_id is required")
    if document_role not in ALLOWED_ROLES:
        raise ValueError(f"unsupported document_role: {document_role!r}")
    if content_type not in ALLOWED_MEDIA:
        raise ValueError(f"unsupported media_type: {content_type!r}")
    if len(data) > MAX_BYTES:
        raise ValueError(
            f"upload too large: {len(data)} bytes exceeds {MAX_BYTES} byte limit"
        )
    if not len(data):
        raise ValueError("upload is empty")
    if not (title or "").strip():
        raise ValueError("title is required")
    for label, value in (
        ("effective_date", effective_date),
        ("period_start", period_start),
        ("period_end", period_end),
    ):
        if value is not None:
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError(f"invalid {label}: {value!r}") from None
    return _normalize_filename(filename)


class DocumentService:
    """Validated document uploads with per-document version history.

    ``dsn`` of None selects the in-memory implementation; otherwise Postgres
    via psycopg. Both modes share validation, hashing, storage paths, and
    same-sha256 idempotency.
    """

    def __init__(self, dsn: str | None, storage: StorageAdapter) -> None:
        self._dsn = dsn
        self._storage = storage
        self._documents: dict[str, DocumentRecord] = {}
        self._versions: dict[str, list[DocumentVersionRecord]] = {}

    # -- public API -------------------------------------------------
    def upload(
        self,
        *,
        organization_id: str,
        user_id: str,
        case_id: str,
        filename: str,
        content_type: str,
        data: bytes,
        document_role: str,
        title: str,
        document_id: str | None = None,
        effective_date: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
    ) -> DocumentVersionRecord:
        safe_name = _validate_upload(
            organization_id=organization_id,
            user_id=user_id,
            case_id=case_id,
            filename=filename,
            content_type=content_type,
            data=data,
            document_role=document_role,
            title=title,
            effective_date=effective_date,
            period_start=period_start,
            period_end=period_end,
        )
        digest = hashlib.sha256(bytes(data)).hexdigest()
        if self._dsn is None:
            return self._memory_upload(
                organization_id=organization_id,
                user_id=user_id,
                case_id=case_id,
                safe_name=safe_name,
                content_type=content_type,
                data=bytes(data),
                document_role=document_role,
                title=title.strip(),
                document_id=document_id,
                effective_date=effective_date,
                period_start=period_start,
                period_end=period_end,
                digest=digest,
            )
        return self._postgres_upload(
            organization_id=organization_id,
            user_id=user_id,
            case_id=case_id,
            safe_name=safe_name,
            content_type=content_type,
            data=bytes(data),
            document_role=document_role,
            title=title.strip(),
            document_id=document_id,
            effective_date=effective_date,
            period_start=period_start,
            period_end=period_end,
            digest=digest,
        )

    def read_bytes(
        self, document_id: str, organization_id: str
    ) -> tuple[DocumentVersionRecord, bytes]:
        """Latest version plus bytes; never leaks foreign-tenant existence."""
        if self._dsn is None:
            return self._memory_read(document_id, organization_id)
        return self._postgres_read(document_id, organization_id)

    def find_location(self, document_id: str) -> dict:
        """Owning case/org plus latest-version metadata for route auth.

        Raises UnknownDocumentError on miss. Returns identifiers and version
        metadata only; never file bytes.
        """
        if self._dsn is None:
            return self._memory_location(document_id)
        return self._postgres_location(document_id)

    # -- memory mode ------------------------------------------------
    def _memory_upload(
        self,
        *,
        organization_id: str,
        user_id: str,
        case_id: str,
        safe_name: str,
        content_type: str,
        data: bytes,
        document_role: str,
        title: str,
        document_id: str | None,
        effective_date: str | None,
        period_start: str | None,
        period_end: str | None,
        digest: str,
    ) -> DocumentVersionRecord:
        _ = (user_id, effective_date, period_start, period_end)
        doc: DocumentRecord | None = None
        if document_id is not None:
            doc = self._documents.get(document_id)
            if doc is not None and doc.organization_id != organization_id:
                raise UnknownDocumentError(document_id)
            if doc is not None:
                for existing in self._versions.get(doc.id, []):
                    if existing.sha256 == digest:
                        return existing
                case_id = doc.case_id
                title = doc.title
        if doc is None:
            doc_id = document_id or str(uuid.uuid4())
            doc = DocumentRecord(
                id=doc_id,
                organization_id=organization_id,
                case_id=case_id,
                document_role=document_role,
                title=title,
            )
            self._documents[doc_id] = doc
            self._versions.setdefault(doc_id, [])
        versions = self._versions[doc.id]
        version_number = max((v.version_number for v in versions), default=0) + 1
        path = f"{organization_id}/{case_id}/{doc.id}/v{version_number}/{safe_name}"
        self._storage.upload(path, data, content_type)
        record = DocumentVersionRecord(
            id=str(uuid.uuid4()),
            document_id=doc.id,
            organization_id=organization_id,
            version_number=version_number,
            storage_path=path,
            sha256=digest,
            byte_size=len(data),
            media_type=content_type,
            extraction_state=classify_upload(content_type, data),
            title=doc.title,
        )
        versions.append(record)
        return record

    def _memory_read(
        self, document_id: str, organization_id: str
    ) -> tuple[DocumentVersionRecord, bytes]:
        doc = self._documents.get(document_id)
        if doc is None or doc.organization_id != organization_id:
            raise UnknownDocumentError(document_id)
        versions = self._versions.get(document_id, [])
        if not versions:
            raise UnknownDocumentError(document_id)
        latest = max(versions, key=lambda v: v.version_number)
        return latest, self._storage.download(latest.storage_path)

    def _memory_location(self, document_id: str) -> dict:
        doc = self._documents.get(document_id)
        if doc is None:
            raise UnknownDocumentError(document_id)
        versions = self._versions.get(document_id, [])
        if not versions:
            raise UnknownDocumentError(document_id)
        latest = max(versions, key=lambda v: v.version_number)
        return {
            "document_id": doc.id,
            "case_id": doc.case_id,
            "organization_id": doc.organization_id,
            "title": doc.title,
            "document_role": doc.document_role,
            "version_id": latest.id,
            "version_number": latest.version_number,
            "sha256": latest.sha256,
            "extraction_state": latest.extraction_state,
            "media_type": latest.media_type,
            "byte_size": latest.byte_size,
        }

    # -- postgres mode ----------------------------------------------
    def _connect(self) -> Any:
        try:
            import psycopg
        except Exception as error:
            raise RuntimeError(
                "psycopg is required for Postgres DocumentService"
            ) from error
        return psycopg.connect(self._dsn, autocommit=False)

    def _postgres_upload(
        self,
        *,
        organization_id: str,
        user_id: str,
        case_id: str,
        safe_name: str,
        content_type: str,
        data: bytes,
        document_role: str,
        title: str,
        document_id: str | None,
        effective_date: str | None,
        period_start: str | None,
        period_end: str | None,
        digest: str,
    ) -> DocumentVersionRecord:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if document_id is not None:
                    document_id = _require_uuid(document_id)
                    cur.execute(
                        "select id, organization_id, case_id, document_role, title"
                        " from public.documents where id = %s for update",
                        (document_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        cur.execute(
                            "insert into public.documents"
                            " (id, organization_id, case_id, document_role,"
                            " title, created_by)"
                            " values (%s, %s, %s, %s, %s, %s)",
                            (
                                document_id,
                                organization_id,
                                case_id,
                                document_role,
                                title,
                                user_id,
                            ),
                        )
                        doc_id, doc_case, doc_title = document_id, case_id, title
                    else:
                        if str(row[1]) != str(organization_id):
                            raise UnknownDocumentError(document_id)
                        doc_id, doc_case, doc_title = str(row[0]), row[2], row[4]
                else:
                    doc_id = str(uuid.uuid4())
                    cur.execute(
                        "insert into public.documents"
                        " (id, organization_id, case_id, document_role,"
                        " title, created_by)"
                        " values (%s, %s, %s, %s, %s, %s)",
                        (
                            doc_id,
                            organization_id,
                            case_id,
                            document_role,
                            title,
                            user_id,
                        ),
                    )
                    doc_case, doc_title = case_id, title
                cur.execute(
                    "select id, document_id, organization_id, version_number,"
                    " storage_path, sha256, byte_size, media_type,"
                    " extraction_state"
                    " from public.document_versions"
                    " where document_id = %s and sha256 = %s",
                    (doc_id, digest),
                )
                dup = cur.fetchone()
                if dup is not None:
                    conn.commit()
                    return DocumentVersionRecord(
                        id=str(dup[0]),
                        document_id=str(dup[1]),
                        organization_id=str(dup[2]),
                        version_number=int(dup[3]),
                        storage_path=dup[4],
                        sha256=dup[5],
                        byte_size=int(dup[6]),
                        media_type=dup[7],
                        extraction_state=dup[8],
                        title=doc_title,
                    )
                cur.execute(
                    "select coalesce(max(version_number), 0)"
                    " from public.document_versions where document_id = %s",
                    (doc_id,),
                )
                version_number = int(cur.fetchone()[0]) + 1
                path = (
                    f"{organization_id}/{doc_case}/{doc_id}"
                    f"/v{version_number}/{safe_name}"
                )
                extraction_state = classify_upload(content_type, data)
                self._storage.upload(path, data, content_type)
                version_id = str(uuid.uuid4())
                cur.execute(
                    "insert into public.document_versions"
                    " (id, organization_id, document_id, version_number,"
                    " storage_bucket, storage_path, sha256, byte_size,"
                    " media_type, effective_date, period_start, period_end,"
                    " extraction_state, uploaded_by)"
                    " values (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
                    " %s::date, %s::date, %s::date, %s, %s)",
                    (
                        version_id,
                        organization_id,
                        doc_id,
                        version_number,
                        STORAGE_BUCKET,
                        path,
                        digest,
                        len(data),
                        content_type,
                        effective_date,
                        period_start,
                        period_end,
                        extraction_state,
                        user_id,
                    ),
                )
                conn.commit()
                return DocumentVersionRecord(
                    id=version_id,
                    document_id=doc_id,
                    organization_id=organization_id,
                    version_number=version_number,
                    storage_path=path,
                    sha256=digest,
                    byte_size=len(data),
                    media_type=content_type,
                    extraction_state=extraction_state,
                    title=doc_title,
                )

    def _postgres_read(
        self, document_id: str, organization_id: str
    ) -> tuple[DocumentVersionRecord, bytes]:
        document_id = _require_uuid(document_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select organization_id, title from public.documents"
                    " where id = %s",
                    (document_id,),
                )
                doc = cur.fetchone()
                if doc is None or str(doc[0]) != str(organization_id):
                    raise UnknownDocumentError(document_id)
                cur.execute(
                    "select id, document_id, organization_id, version_number,"
                    " storage_path, sha256, byte_size, media_type,"
                    " extraction_state"
                    " from public.document_versions"
                    " where document_id = %s"
                    " order by version_number desc limit 1",
                    (document_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise UnknownDocumentError(document_id)
                record = DocumentVersionRecord(
                    id=str(row[0]),
                    document_id=str(row[1]),
                    organization_id=str(row[2]),
                    version_number=int(row[3]),
                    storage_path=row[4],
                    sha256=row[5],
                    byte_size=int(row[6]),
                    media_type=row[7],
                    extraction_state=row[8],
                    title=doc[1],
                )
                path = row[4]
        return record, self._storage.download(path)

    def _postgres_location(self, document_id: str) -> dict:
        document_id = _require_uuid(document_id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select id, organization_id, case_id, document_role, title"
                    " from public.documents where id = %s",
                    (document_id,),
                )
                doc = cur.fetchone()
                if doc is None:
                    raise UnknownDocumentError(document_id)
                cur.execute(
                    "select id, version_number, sha256, byte_size, media_type,"
                    " extraction_state"
                    " from public.document_versions"
                    " where document_id = %s"
                    " order by version_number desc limit 1",
                    (document_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise UnknownDocumentError(document_id)
                return {
                    "document_id": str(doc[0]),
                    "case_id": str(doc[2]),
                    "organization_id": str(doc[1]),
                    "title": doc[4],
                    "document_role": doc[3],
                    "version_id": str(row[0]),
                    "version_number": int(row[1]),
                    "sha256": row[2],
                    "extraction_state": row[5],
                    "media_type": row[4],
                    "byte_size": int(row[3]),
                }
