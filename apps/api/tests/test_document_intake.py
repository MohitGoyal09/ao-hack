"""Document intake service tests (service level only, no routes/agents)."""

from __future__ import annotations

import os
import unittest
import uuid
from unittest.mock import patch

from src.covenant import documents as documents_module
from src.covenant.documents import (
    ALLOWED_MEDIA,
    ALLOWED_ROLES,
    MAX_BYTES,
    DocumentService,
    UnknownDocumentError,
    classify_upload,
)
from src.platform.storage import (
    MemoryStorageAdapter,
    SupabaseStorageAdapter,
    storage_adapter_from_env,
)

CSV_BYTES = b"period,amount\n2026-01,100.00\n2026-02,200.00\n"
CSV_BYTES_V2 = b"period,amount\n2026-01,110.00\n2026-02,210.00\n"


def _svc(**kwargs) -> DocumentService:
    storage = kwargs.pop("storage", None) or MemoryStorageAdapter()
    return DocumentService(None, storage)


def _upload_kwargs(**overrides):
    kwargs = {
        "organization_id": "org-1",
        "user_id": "user-1",
        "case_id": "case-1",
        "filename": "statement.csv",
        "content_type": "text/csv",
        "data": CSV_BYTES,
        "document_role": "financial_statement",
        "title": "Q1 statement",
    }
    kwargs.update(overrides)
    return kwargs


class StorageAdapterTests(unittest.TestCase):
    def test_memory_roundtrip(self) -> None:
        storage = MemoryStorageAdapter()
        storage.upload("a/b.txt", b"hello", "text/plain")
        self.assertEqual(storage.download("a/b.txt"), b"hello")

    def test_memory_missing_raises_file_not_found(self) -> None:
        with self.assertRaises(FileNotFoundError):
            MemoryStorageAdapter().download("nope/missing.bin")

    def test_factory_returns_memory_without_client(self) -> None:
        self.assertIsInstance(
            storage_adapter_from_env(None), MemoryStorageAdapter
        )

    def test_factory_returns_supabase_with_client(self) -> None:
        from unittest.mock import MagicMock

        adapter = storage_adapter_from_env(MagicMock())
        self.assertIsInstance(adapter, SupabaseStorageAdapter)


class DocumentConstantsTests(unittest.TestCase):
    def test_allowed_roles_and_media(self) -> None:
        self.assertEqual(
            set(ALLOWED_ROLES),
            {
                "credit_agreement",
                "amendment",
                "financial_statement",
                "supporting_evidence",
                "certificate_form",
            },
        )
        self.assertEqual(
            set(ALLOWED_MEDIA),
            {
                "application/pdf",
                "application/json",
                "text/csv",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "text/plain",
                "text/html",
            },
        )
        self.assertEqual(MAX_BYTES, 50 * 1024 * 1024)

    def test_classify_textual_uploads_pending(self) -> None:
        for media in (
            "text/csv",
            "application/json",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ):
            self.assertEqual(classify_upload(media, b"a,b\n1,2\n"), "pending")

    def test_classify_unparseable_pdf_needs_ocr(self) -> None:
        self.assertEqual(
            classify_upload("application/pdf", b"not a real pdf"), "needs_ocr"
        )

    def test_classify_unknown_media_unsupported(self) -> None:
        self.assertEqual(classify_upload("image/png", b"\x89PNG"), "unsupported")


class MemoryDocumentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = MemoryStorageAdapter()
        self.svc = DocumentService(None, self.storage)

    def test_first_upload_creates_v1_pending(self) -> None:
        version = self.svc.upload(**_upload_kwargs())
        self.assertEqual(version.version_number, 1)
        self.assertEqual(version.extraction_state, "pending")
        self.assertEqual(version.media_type, "text/csv")
        self.assertEqual(version.byte_size, len(CSV_BYTES))
        self.assertEqual(len(version.sha256), 64)
        self.assertEqual(
            version.storage_path,
            f"org-1/case-1/{version.document_id}/v1/statement.csv",
        )
        record, data = self.svc.read_bytes(version.document_id, "org-1")
        self.assertEqual(record.id, version.id)
        self.assertEqual(data, CSV_BYTES)

    def test_second_upload_same_document_creates_v2(self) -> None:
        v1 = self.svc.upload(**_upload_kwargs())
        v2 = self.svc.upload(
            **_upload_kwargs(data=CSV_BYTES_V2, document_id=v1.document_id)
        )
        self.assertEqual(v2.document_id, v1.document_id)
        self.assertEqual(v2.version_number, 2)
        self.assertNotEqual(v2.id, v1.id)
        self.assertNotEqual(v2.sha256, v1.sha256)
        latest, data = self.svc.read_bytes(v1.document_id, "org-1")
        self.assertEqual(latest.version_number, 2)
        self.assertEqual(data, CSV_BYTES_V2)

    def test_same_bytes_reupload_returns_same_version(self) -> None:
        v1 = self.svc.upload(**_upload_kwargs())
        again = self.svc.upload(
            **_upload_kwargs(document_id=v1.document_id)
        )
        self.assertEqual(again.id, v1.id)
        self.assertEqual(again.version_number, 1)
        versions = self.svc._versions[v1.document_id]  # noqa: SLF001
        self.assertEqual(len(versions), 1)

    def test_bad_role_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.upload(**_upload_kwargs(document_role="board_deck"))

    def test_bad_media_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.upload(**_upload_kwargs(content_type="image/png"))

    def test_oversize_raises(self) -> None:
        with patch.object(documents_module, "MAX_BYTES", 8):
            with self.assertRaises(ValueError):
                self.svc.upload(**_upload_kwargs())

    def test_traversal_filename_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.svc.upload(**_upload_kwargs(filename="../secret.csv"))
        with self.assertRaises(ValueError):
            self.svc.upload(**_upload_kwargs(filename="   "))

    def test_foreign_org_read_raises_without_leak(self) -> None:
        version = self.svc.upload(**_upload_kwargs())
        with self.assertRaises(UnknownDocumentError):
            self.svc.read_bytes(version.document_id, "other-org")
        with self.assertRaises(UnknownDocumentError):
            self.svc.read_bytes(str(uuid.uuid4()), "org-1")
        self.assertTrue(issubclass(UnknownDocumentError, LookupError))

    def test_malformed_ids_raise_unknown_document(self) -> None:
        with self.assertRaises(UnknownDocumentError):
            self.svc.find_location("not-a-uuid")
        with self.assertRaises(UnknownDocumentError):
            self.svc.read_bytes("not-a-uuid!!", "org-1")


def _provision_org_case(cur, org: str, user: str, case_id: str) -> None:
    cur.execute(
        "insert into auth.users (id) values (%s) on conflict (id) do nothing",
        (user,),
    )
    cur.execute(
        "insert into public.organizations (id, name, slug, created_by)"
        " values (%s, %s, %s, %s) on conflict (id) do nothing",
        (org, f"org-{org[:8]}", f"doc-{org[:8]}", user),
    )
    cur.execute(
        "insert into public.organization_members (organization_id, user_id, role)"
        " values (%s, %s, 'treasury_reviewer') on conflict do nothing",
        (org, user),
    )
    cur.execute(
        "insert into public.covenant_cases"
        " (id, organization_id, name, borrower_name, facility_name, created_by)"
        " values (%s, %s, %s, %s, %s, %s) on conflict (id) do nothing",
        (case_id, org, case_id, "borrower", "facility", user),
    )


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "TEST_DATABASE_URL is not configured")
class PostgresDocumentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        import psycopg

        self.dsn = os.environ["TEST_DATABASE_URL"]
        self.storage = MemoryStorageAdapter()
        self.org = str(uuid.uuid4())
        self.user = str(uuid.uuid4())
        self.case_id = str(uuid.uuid4())
        with psycopg.connect(self.dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                _provision_org_case(cur, self.org, self.user, self.case_id)

    def _service(self) -> DocumentService:
        return DocumentService(self.dsn, self.storage)

    def _kwargs(self, **overrides):
        kwargs = _upload_kwargs(
            organization_id=self.org,
            user_id=self.user,
            case_id=self.case_id,
        )
        kwargs.update(overrides)
        return kwargs

    def test_version_history_survives_reconstruction(self) -> None:
        svc = self._service()
        v1 = svc.upload(**self._kwargs())
        self.assertEqual(v1.version_number, 1)
        v2 = svc.upload(
            **self._kwargs(data=CSV_BYTES_V2, document_id=v1.document_id)
        )
        self.assertEqual(v2.version_number, 2)
        same = svc.upload(
            **self._kwargs(data=CSV_BYTES_V2, document_id=v1.document_id)
        )
        self.assertEqual(same.id, v2.id)

        rebuilt = self._service()
        latest, data = rebuilt.read_bytes(v1.document_id, self.org)
        self.assertEqual(latest.version_number, 2)
        self.assertEqual(latest.sha256, v2.sha256)
        self.assertEqual(data, CSV_BYTES_V2)

    def test_postgres_rejects_bad_role_media_oversize(self) -> None:
        svc = self._service()
        with self.assertRaises(ValueError):
            svc.upload(**self._kwargs(document_role="board_deck"))
        with self.assertRaises(ValueError):
            svc.upload(**self._kwargs(content_type="image/png"))
        with patch.object(documents_module, "MAX_BYTES", 8):
            with self.assertRaises(ValueError):
                svc.upload(**self._kwargs())

    def test_postgres_foreign_org_read_raises(self) -> None:
        svc = self._service()
        version = svc.upload(**self._kwargs())
        with self.assertRaises(UnknownDocumentError):
            svc.read_bytes(version.document_id, str(uuid.uuid4()))

    def test_postgres_malformed_ids_raise_unknown_document(self) -> None:
        svc = self._service()
        with self.assertRaises(UnknownDocumentError):
            svc.read_bytes("not-a-uuid", self.org)
        with self.assertRaises(UnknownDocumentError):
            svc.find_location("not-a-uuid")
        with self.assertRaises(UnknownDocumentError):
            svc.upload(**self._kwargs(document_id="not-a-uuid"))


if __name__ == "__main__":
    unittest.main()
