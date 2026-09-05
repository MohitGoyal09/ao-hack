import unittest

from src.platform.observability import NeatlogsObserver
from src.platform.supabase import AuthenticationError, SupabasePlatform


class PlatformAdapterTests(unittest.TestCase):
    def test_offline_platform_provides_explicit_demo_principal(self):
        platform = SupabasePlatform(client=None, bucket="covenant-private")

        principal = platform.authenticate(None)

        self.assertFalse(platform.enabled)
        self.assertEqual(principal.user_id, "demo-user")
        self.assertEqual(principal.role, "treasury_reviewer")

    def test_configured_supabase_requires_bearer_token(self):
        platform = SupabasePlatform(client=object(), bucket="covenant-private")

        with self.assertRaises(AuthenticationError):
            platform.authenticate(None)
        with self.assertRaises(AuthenticationError):
            platform.authenticate("Basic not-accepted")

    def test_disabled_observability_is_safe_noop(self):
        observer = NeatlogsObserver(
            enabled=False,
            api_key="",
            endpoint="https://ingest.neatlogs.com",
            workflow_name="test",
        )

        observer.initialize()
        with observer.workflow_span("case-id"):
            observer.record_outcome("case-id", "run-id", "NEEDS_REVIEW")
        observer.shutdown()

        self.assertFalse(observer.enabled)
        self.assertEqual(observer.callbacks(), [])
