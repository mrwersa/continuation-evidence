"""Fail-closed study orchestration. Network access is supplied by an adapter.

Journal events are durable before side effects. An existing journal is never
resumed: interrupted calls and mutations require manual evidence reconciliation.
"""
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from design import schedule


class Stop(RuntimeError):
    pass


class Journal:
    def __init__(self, path):
        self.handle = Path(path).open("x", encoding="utf-8")

    def write(self, kind, **fields):
        self.handle.write(json.dumps({"kind": kind, "utc": datetime.now(timezone.utc).isoformat(), **fields}) + "\n")
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def close(self):
        self.handle.close()


class Guard:
    def __init__(self, start, expiry, prior_gbp, hourly_gbp, fixed_gbp, clock=time.time):
        values = (start, expiry, prior_gbp, hourly_gbp, fixed_gbp)
        if not all(math.isfinite(x) for x in values):
            raise Stop("Non-finite resource estimate")
        if min(prior_gbp, hourly_gbp, fixed_gbp) < 0 or hourly_gbp == 0:
            raise Stop("Invalid resource estimate")
        if expiry - start < 8 * 3600:
            raise Stop("Fewer than eight hours before quota expiry")
        self.start, self.expiry, self.clock = start, expiry, clock
        self.prior, self.hourly, self.fixed = prior_gbp, hourly_gbp, fixed_gbp
        self.calls = 0
        self.check()

    def check(self, new_sequence=False):
        now = self.clock()
        if now < self.start or now >= min(self.start + 8 * 3600, self.expiry):
            raise Stop("Traffic deadline or invalid clock")
        if new_sequence and now >= self.start + 7 * 3600:
            raise Stop("New-sequence deadline")
        # Reserve the full twelve-hour cleanup envelope, not only cost to date.
        if self.prior + self.fixed + 12 * self.hourly >= 5:
            raise Stop("Cumulative projected operating stop")

    def reserve(self):
        self.check()
        if self.calls >= 500:
            raise Stop("Tool-call ceiling")
        self.calls += 1
        return self.calls


def classify(row, request, revision, limit, expiry, is_tool=True):
    """Verify transport, native headers and independent dispatch before scoring."""
    if row.get("delivery") != "response_received":
        raise Stop("Uncertain dispatch")
    headers = {k.lower(): str(v) for k, v in row.get("headers", {}).items()}
    if headers.get("x-smoke-revision") != str(revision):
        raise Stop("Wrong revision")
    try:
        body = json.loads(row["body"])
        if is_tool:
            if int(headers["x-smoke-limit"]) != limit:
                raise Stop("Wrong limit")
            if int(headers["x-smoke-expiry"]) != expiry:
                raise Stop("Changed window")
            used = int(headers["x-smoke-used"])
            available = int(headers["x-smoke-available"])
        else:
            used = available = None
    except (ValueError, KeyError, TypeError) as exc:
        raise Stop("Missing or malformed native evidence") from exc
    receipts = row.get("backend_matches")
    if not isinstance(receipts, list):
        raise Stop("Missing backend audit")
    fault = body.get("fault", {}).get("detail", {}).get("errorcode")
    if fault == "policies.ratelimit.QuotaViolation" and is_tool:
        if receipts:
            raise Stop("Refusal dispatched to backend")
        outcome = "refuse"
    elif row.get("status") == 200 and "result" in body and not body["result"].get("isError", False):
        if body.get("id") != request["id"] or len(receipts) != 1 or receipts[0].get("request") != request:
            raise Stop("Duplicate, missing or changed backend receipt")
        if is_tool:
            try:
                receipt = json.loads(body["result"]["content"][0]["text"])
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise Stop("Malformed synthetic receipt") from exc
            if receipt != {"receipt": request["id"], "amount": request["params"]["arguments"]["amount"], "effect": "none"}:
                raise Stop("Changed synthetic receipt")
        outcome = "admit"
    else:
        raise Stop("Technical response, not quota refusal")
    return {"outcome": outcome, "used": used, "available": available}


class Runner:
    def __init__(self, adapter, journal, guard, sleep=time.sleep):
        self.api, self.log, self.guard, self.sleep = adapter, journal, guard, sleep
        self.variant = self.revision = None
        self.limit = 1000
        self.diagnostics = 0

    def pause(self, seconds):
        remaining = seconds
        while remaining:
            self.guard.check()
            chunk = min(15, remaining)
            self.sleep(chunk)
            remaining -= chunk
        self.guard.check()

    def call(self, key, amount, stage, method="tools/call"):
        self.guard.check()
        request = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": method}
        count = self.guard.calls
        if method == "tools/call":
            if type(amount) is not int or not 1 <= amount <= 1000:
                raise Stop("Invalid amount")
            count = self.guard.reserve()
            request["params"] = {"name": "refund", "arguments": {"amount": amount}}
        elif method == "initialize":
            request["params"] = {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "controlled-study", "version": "1"}}
        elif method != "tools/list":
            raise Stop("Unapproved method")
        self.log.write("call_reserved", stage=stage, task=key, request=request, calls=count)
        try:
            row = self.api.request(key, request)
        except Exception as exc:
            self.log.write("uncertain_call", request_id=request["id"], error=type(exc).__name__)
            raise Stop("Transport failed, no retry") from exc
        self.log.write("response", stage=stage, task=key, request=request, response=row)
        result = classify(row, request, self.revision, self.limit, int(self.guard.expiry * 1000), method == "tools/call")
        self.log.write("classification", request_id=request["id"], **result)
        return result

    def deploy(self, variant, stage):
        self.guard.check()
        self.log.write("import_reserved", variant=variant, stage=stage, previous_revision=self.revision)
        try:
            revision = str(self.api.import_bundle(variant))
        except Exception as exc:
            self.log.write("uncertain_import", stage=stage, error=type(exc).__name__)
            raise Stop("Import unresolved, no retry") from exc
        if not revision.isdigit():
            raise Stop("Malformed revision")
        self.log.write("import_returned", variant=variant, revision=revision)
        self.guard.check()
        self.log.write("promotion_reserved", revision=revision, variant=variant)
        write_error = None
        try:
            self.api.promote(revision)
        except Exception as exc:
            write_error = type(exc).__name__
            self.log.write("promotion_write_error", revision=revision, error=write_error)
        # Even a timed-out mutation is observed, never submitted a second time.
        deadline = self.guard.clock() + 600
        while True:
            self.guard.check()
            status = self.api.deployment(revision)
            self.log.write("deployment_observation", revision=revision, status=status)
            if status.get("revision") == revision and status.get("state") == "READY":
                break
            if self.guard.clock() >= deadline:
                raise Stop("Unverified management mutation")
            self.pause(15)
        self.variant, self.revision = variant, revision
        self.limit = {"tighten700": 700, "tighten500": 500}.get(variant, 1000)
        self.diagnostics += 1
        amount = {1000: 1, 700: 800, 500: 600}[self.limit]
        result = self.call(f"study-diag-{self.diagnostics:03d}", amount, stage + "/diagnostic")
        expected = "admit" if self.limit == 1000 else "refuse"
        if result["outcome"] != expected or result["used"] != (1 if expected == "admit" else 0):
            raise Stop("Deployment diagnostic failed")

    def preflight(self):
        self.deploy("baseline", "calibration")
        self.call("study-calibration", None, "initialise", "initialize")
        self.call("study-calibration", None, "discover", "tools/list")
        for amount, outcome, used in [(600, "admit", 600), (600, "refuse", 600), (300, "admit", 900)]:
            result = self.call("study-calibration", amount, "calibration")
            if result["outcome"] != outcome or result["used"] != used:
                raise Stop("Baseline calibration failed")
        for amount in (1000, 1):
            self.call("study-equality", amount, "equality_observation")
        self.log.write("preflight_complete")

    def collect(self, trials=None):
        trials = schedule() if trials is None else trials
        completed = set()
        current = None
        try:
            self.preflight()
            for trial in trials:
                current = trial["id"]
                self.guard.check(new_sequence=True)
                self.log.write("sequence_started", trial=trial)
                if trial["uses_parent_deployment"]:
                    if trial["uses_parent_deployment"] not in completed or self.variant != "tighten700":
                        self.log.write("sequence_status", id=current, status="blocked", reason="Parent deployment unavailable")
                        completed.add(current)
                        continue
                elif self.variant != "baseline":
                    self.deploy("baseline", current + "/restore")
                key = trial["accounting_key"]
                preload_end = None
                for amount in trial["preload"]:
                    result = self.call(key, amount, current + "/preload")
                    if result["outcome"] != "admit" or result["used"] != 600:
                        raise Stop("Fresh-key preload calibration failed")
                    preload_end = self.guard.clock()
                if trial["focal_variant"] is not None:
                    self.deploy(trial["focal_variant"], current + "/focal")
                elif trial["arm"] == "no_update":
                    self.log.write("control_wait", id=current, seconds=120)
                    self.pause(120)
                self.log.write("probe_start", id=current, preload_gap_seconds=None if preload_end is None else self.guard.clock() - preload_end)
                outcomes = [self.call(key, amount, current + f"/probe-{i+1}") for i, amount in enumerate(trial["probes"])]
                # Unexpected but verified scientific outcomes are retained, not aborted.
                self.log.write("sequence_status", id=current, status="complete", outcomes=outcomes)
                completed.add(current)
                current = None
            self.log.write("collection_complete", sequences=len(completed), calls=self.guard.calls)
            return True
        except Exception as exc:
            self.log.write("collection_aborted", error=type(exc).__name__, reason=str(exc), current=current, calls=self.guard.calls)
            for trial in trials:
                if trial["id"] not in completed:
                    status = "truncated" if trial["id"] == current else "not_started"
                    if trial["uses_parent_deployment"] == current:
                        status = "blocked"
                    self.log.write("sequence_status", id=trial["id"], status=status, reason=str(exc))
            return False
