"""Expiry-aware workstation credentials. No network or subprocess on import."""
import json
import subprocess
import time
from datetime import datetime, timezone


class CredentialError(RuntimeError):
    """Safe to log: messages never contain credential material."""


class Credentials:
    margin_seconds = 300

    def __init__(self, account, clock=time.time, run=subprocess.run):
        if not isinstance(account, str) or not account or account.startswith("-"):
            raise CredentialError("An explicit personal account is required")
        self.account, self.clock, self.run = account, clock, run
        self._token = None
        self.expiry = 0
        self.obtained = 0
        self.refreshes = 0

    def token(self):
        now = self.clock()
        if self._token and self.obtained <= now < self.expiry - self.margin_seconds:
            return self._token
        # Clear stale credentials before refresh so failure cannot fall back.
        self._token = None
        command = ["gcloud", "config", "config-helper", "--format=json",
                   "--force-auth-refresh", "--account=" + self.account,
                   "--project=your-gcp-project", "--quiet"]
        try:
            result = self.run(command, capture_output=True, text=True,
                              check=True, timeout=45)
            data = json.loads(result.stdout)
            credential = data["credential"]
            token = credential["access_token"]
            expiry = datetime.strptime(credential["token_expiry"],
                                       "%Y-%m-%dT%H:%M:%SZ").replace(
                                           tzinfo=timezone.utc).timestamp()
            if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                raise ValueError("Invalid token")
            now = self.clock()
            if expiry - now <= self.margin_seconds:
                raise ValueError("Insufficient lifetime")
        except Exception:
            # Subprocess errors can include stdout. Do not chain or log them.
            raise CredentialError("Credential refresh failed or returned unusable expiry") from None
        self._token, self.expiry, self.obtained = token, expiry, now
        self.refreshes += 1
        return token
