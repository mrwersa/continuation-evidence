"""Offline tests. Credentials are fabricated and no command is executed."""
import json
import subprocess
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from credentials import Credentials, CredentialError


def response(expiry, token="fabricated-token"):
    stamp = datetime.fromtimestamp(expiry, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return SimpleNamespace(stdout=json.dumps({"credential": {
        "access_token": token, "token_expiry": stamp}}))


class CredentialTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000
        self.run = Mock(return_value=response(4600))
        self.auth = Credentials("researcher@example.invalid", lambda: self.now, self.run)

    def test_refresh_uses_reported_expiry_not_retrieval_time(self):
        self.run.side_effect = [response(1400, "first"), response(4800, "second")]
        self.assertEqual(self.auth.token(), "first")
        self.now = 1099
        self.assertEqual(self.auth.token(), "first")
        self.now = 1100
        self.assertEqual(self.auth.token(), "second")
        self.assertEqual(self.run.call_count, 2)
        self.assertIn("--force-auth-refresh", self.run.call_args.args[0])

    def test_fresh_retrieval_of_almost_expired_token_is_rejected(self):
        self.run.return_value = response(1299)
        with self.assertRaises(CredentialError):
            self.auth.token()
        self.assertIsNone(self.auth._token)

    def test_refresh_failure_cannot_reuse_old_token(self):
        self.auth.token()
        self.now = 4300
        self.run.side_effect = subprocess.CalledProcessError(
            1, "gcloud", output="secret-output", stderr="secret-error")
        with self.assertRaises(CredentialError) as caught:
            self.auth.token()
        self.assertIsNone(self.auth._token)
        self.assertNotIn("secret", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_missing_malformed_empty_and_expired_credentials_fail(self):
        samples = ["not-json", "{}", json.dumps({"credential": {}}),
                   response(999).stdout, response(5000, "").stdout,
                   response(5000, "bad\nheader").stdout]
        for raw in samples:
            with self.subTest(raw=raw):
                self.run.return_value = SimpleNamespace(stdout=raw)
                with self.assertRaises(CredentialError):
                    self.auth.token()

    def test_refresh_timeout_is_bounded_and_not_retried(self):
        self.run.side_effect = subprocess.TimeoutExpired("gcloud", 45)
        with self.assertRaises(CredentialError):
            self.auth.token()
        self.assertEqual(self.run.call_count, 1)
        self.assertEqual(self.run.call_args.kwargs["timeout"], 45)

    def test_clock_rollback_forces_refresh(self):
        self.auth.token()
        self.now = 999
        self.auth.token()
        self.assertEqual(self.run.call_count, 2)

    def test_eight_hour_simulation_refreshes_without_sleeping(self):
        self.run.side_effect = lambda *a, **k: response(self.now + 3600)
        for self.now in range(1000, 1000 + 8 * 3600, 15):
            self.assertEqual(self.auth.token(), "fabricated-token")
            self.assertGreater(self.auth.expiry - self.now, 300)
        self.assertGreaterEqual(self.auth.refreshes, 8)


if __name__ == "__main__":
    unittest.main()
