"""Reuse the preserved scientific runner with new credentials and safety guards."""
import hashlib
import json
import math
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from credentials import Credentials
from task_keys import namespaced

ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT.parent / "gcp_mcp_study"


def check_dependencies():
    pins = json.loads((ROOT / "dependencies.json").read_text())
    for name, digest in pins["sha256"].items():
        path = (ROOT.parent / name).resolve()
        if not path.is_relative_to(ROOT.parent) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError("Changed repeat dependency: " + name)


check_dependencies()
sys.path.append(str(ORIGINAL))
from runner import Guard as OriginalGuard, Journal, Runner as OriginalRunner, Stop
from live import Adapter as OriginalAdapter


class Guard(OriginalGuard):
    def __init__(self, start, expiry, prior_gbp, hourly_gbp, fixed_gbp, clock=time.time):
        self.prior_total = prior_gbp
        # The original guard remains a conservative £5 guard for this run.
        # The cumulative £20 guard is separate, not a renewed £20 allowance.
        if not math.isfinite(prior_gbp) or prior_gbp < 0:
            raise Stop("Invalid prior-cost bound")
        super().__init__(start, expiry, 0, hourly_gbp, fixed_gbp, clock)

    def check(self, new_sequence=False):
        super().check(new_sequence)
        if self.prior_total + self.fixed + 12 * self.hourly >= 20:
            raise Stop("Cumulative £20 ceiling")


class Management:
    def __init__(self, journal, credentials, clock=time.time, send=None):
        self.log, self.credentials, self.clock = journal, credentials, clock
        self.send = urllib.request.urlopen if send is None else send

    def request(self, method, path, data=None, content_type="application/json"):
        base = "organizations/your-gcp-project"
        if (path != base and not path.startswith(base + "/")) or ".." in path or "#" in path:
            raise Stop("Out-of-scope management path")
        if method not in ("GET", "POST"):
            raise Stop("Unsupported study management method")
        before = self.credentials.refreshes
        token = self.credentials.token()
        if self.credentials.refreshes != before:
            self.log.write("credential_refreshed", expiry_epoch=self.credentials.expiry,
                           remaining_seconds=self.credentials.expiry - self.clock())
        self.log.write("management_reserved", method=method, path=path,
                       body_sha256=hashlib.sha256(data).hexdigest() if data else None)
        request = urllib.request.Request("https://apigee.googleapis.com/v1/" + path,
            data=data, method=method, headers={"Authorization": "Bearer " + token,
            "Content-Type": content_type, "x-goog-user-project": "your-gcp-project"})
        try:
            response = self.send(request, timeout=60)
        except urllib.error.HTTPError as exc:
            response = exc
        except Exception:
            self.log.write("management_transport_uncertain", method=method, path=path)
            raise Stop("Management transport failed, no replay") from None
        with response:
            try:
                payload = json.load(response)
            except Exception:
                self.log.write("management_malformed_response", method=method, path=path,
                               status=response.status)
                raise Stop("Malformed management response, no replay") from None
            self.log.write("management_response", method=method, path=path,
                           status=response.status, payload=payload)
            if response.status >= 400:
                raise Stop(f"Management HTTP {response.status}, no replay")
            return payload


class Adapter(OriginalAdapter):
    def __init__(self, config, journal):
        self.config, self.log = config, journal
        self.manager = Management(journal, Credentials(config["account"]))

    def request(self, key, request):
        from task_keys import KEY
        if not isinstance(key, str) or not KEY.fullmatch(key):
            raise Stop("Task key violates deployed validator before remote dispatch")
        command = ["gcloud", "compute", "ssh", "mcp-lab-client", "--project=your-gcp-project",
                   "--account=" + self.config["account"], "--zone=europe-west2-a",
                   "--tunnel-through-iap", "--quiet",
                   "--ssh-key-file=" + self.config["ssh_key_file"],
                   "--command=cd /tmp/mcp-study && python3 remote_call.py"]
        from integration import dispatch
        secret = Path(self.config["api_key_file"]).read_text().strip()
        def diagnostic(row):
            kind = row.pop("kind")
            self.log.write(kind, **row)
        return dispatch(command, {"task": key, "request": request},
                        diagnostic, [secret], run=subprocess.run)



class Runner(OriginalRunner):
    def __init__(self, adapter, journal, guard, execution_id, sleep=time.sleep):
        if not re.fullmatch(r"repeat-[0-9]{8}-[a-z0-9]{8}", execution_id):
            raise Stop("Invalid fresh execution identifier")
        self.execution_id = execution_id
        super().__init__(adapter, journal, guard, sleep)

    def call(self, key, amount, stage, method="tools/call"):
        # Apply once to every key, including inherited diagnostic/calibration keys.
        return super().call(namespaced(self.execution_id, key), amount, stage, method)
