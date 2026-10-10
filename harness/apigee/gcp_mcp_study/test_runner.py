"""Offline fault injection. No provider calls, sleeping or credentials."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from design import schedule
from runner import Guard, Journal, Runner, Stop, classify


class Clock:
    now = 1000
    def __call__(self):
        return self.now
    def sleep(self, seconds):
        self.now += seconds


class Fake:
    def __init__(self, expiry):
        self.revision = 0
        self.limit = 1000
        self.name = "RefundQuota"
        self.counts = {}
        self.expiry = expiry
        self.imports = self.promotions = self.requests = 0
        self.failure = None
        self.ready = True
        self.corrupt = None

    def import_bundle(self, variant):
        self.imports += 1
        if self.failure == "import":
            raise TimeoutError()
        self.revision += 1
        self.limit = {"tighten700": 700, "tighten500": 500}.get(variant, 1000)
        self.name = "Renamed" if variant == "rename_policy" else "RefundQuota"
        return str(self.revision)

    def promote(self, revision):
        self.promotions += 1
        if self.failure == "promote":
            raise TimeoutError()

    def deployment(self, revision):
        return {"revision": revision, "state": "READY" if self.ready else "PROGRESSING"}

    def request(self, key, req):
        self.requests += 1
        if self.failure == "request":
            raise TimeoutError()
        tool = req["method"] == "tools/call"
        account = (self.name, key)
        used = self.counts.get(account, 0)
        amount = req.get("params", {}).get("arguments", {}).get("amount", 0)
        permit = used + amount <= self.limit
        if permit and tool:
            used += amount
            self.counts[account] = used
        if permit:
            result = {"content": [{"type": "text", "text": json.dumps({"receipt": req["id"], "amount": amount, "effect": "none"})}], "isError": False} if tool else {}
            body = {"jsonrpc": "2.0", "id": req["id"], "result": result}
        else:
            body = {"fault": {"detail": {"errorcode": "policies.ratelimit.QuotaViolation"}}}
        row = {"delivery": "response_received", "status": 200 if permit else 500,
               "body": json.dumps(body), "backend_matches": [{"request": copy.deepcopy(req)}] if permit else [],
               "headers": {"x-smoke-revision": str(self.revision), "x-smoke-limit": str(self.limit),
                           "x-smoke-used": str(used), "x-smoke-available": str(self.limit-used),
                           "x-smoke-expiry": str(self.expiry)}}
        if self.corrupt:
            self.corrupt(row)
        return row


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "events.jsonl"
        self.clock = Clock()
        self.clock.now = 1000
        self.guard = Guard(1000, 87400, 0.1, 0.1, 1, self.clock)
        self.log = Journal(self.path)
        self.addCleanup(self.log.close)
        self.api = Fake(87400000)
        self.runner = Runner(self.api, self.log, self.guard, self.clock.sleep)

    def rows(self):
        return [json.loads(x) for x in self.path.read_text().splitlines()]

    def test_full_schedule_and_name_scope_are_recorded(self):
        self.assertTrue(self.runner.collect())
        rows = self.rows()
        complete = [r for r in rows if r["kind"] == "sequence_status" and r["status"] == "complete"]
        self.assertEqual(len(complete), 90)
        self.assertEqual(self.api.promotions, 110)
        self.assertEqual(self.guard.calls, 365)  # 250 core, 110 diagnostic, 5 calibration
        rename = [r for r in complete if "rename_policy" in r["id"]]
        self.assertTrue(all([x["used"] for x in r["outcomes"]] == [300, 500] for r in rename))
        self.assertEqual(len([r for r in rows if r["kind"] == "control_wait"]), 10)

    def test_uncertain_tool_is_not_retried(self):
        self.api.failure = "request"
        self.assertFalse(self.runner.collect())
        self.assertEqual(self.api.requests, 1)
        self.assertEqual(self.guard.calls, 1)
        self.assertEqual(sum(r["kind"] == "call_reserved" for r in self.rows()), 1)

    def test_interrupted_import_is_not_retried(self):
        self.api.failure = "import"
        self.assertFalse(self.runner.collect())
        self.assertEqual(self.api.imports, 1)
        self.assertEqual(self.api.promotions, 0)

    def test_timed_out_promotion_is_observed_without_rewrite(self):
        self.api.failure = "promote"
        self.runner.deploy("baseline", "test")
        self.assertEqual(self.api.promotions, 1)
        self.assertEqual(self.runner.revision, "1")

    def test_unresolved_promotion_stops(self):
        self.api.failure = "promote"
        self.api.ready = False
        self.assertFalse(self.runner.collect())
        self.assertEqual(self.api.promotions, 1)
        self.assertEqual(self.api.requests, 0)
        self.assertEqual(self.clock.now, 1600)

    def test_wrong_revision_window_limit_and_duplicate_dispatch_stop(self):
        for header, value in [("x-smoke-revision", "99"), ("x-smoke-expiry", "0"), ("x-smoke-limit", "99")]:
            with self.subTest(header=header):
                self.api.corrupt = lambda r, h=header, v=value: r["headers"].update({h: v})
                with self.assertRaises(Stop):
                    self.runner.deploy("baseline", "test")
        self.api.corrupt = lambda r: r["backend_matches"].extend(copy.deepcopy(r["backend_matches"]))
        with self.assertRaisesRegex(Stop, "Duplicate"):
            self.runner.deploy("baseline", "test")

    def test_technical_error_is_not_refusal(self):
        self.api.corrupt = lambda r: r.update(status=401, body="{}", backend_matches=[])
        with self.assertRaisesRegex(Stop, "Technical"):
            self.runner.deploy("baseline", "test")

    def test_hard_call_and_time_caps(self):
        self.guard.calls = 500
        with self.assertRaises(Stop):
            self.guard.reserve()
        self.clock.now = 1000 + 7 * 3600
        self.guard.check()
        with self.assertRaises(Stop):
            self.guard.check(new_sequence=True)
        self.clock.now += 3600
        with self.assertRaises(Stop):
            self.guard.check()

    def test_budget_and_window_gate(self):
        for args in [(1000, 2000, 0, .1, 1), (1000, 87400, 4, .1, 1), (1000, 87400, 0, float("nan"), 1)]:
            with self.subTest(args=args), self.assertRaises(Stop):
                Guard(*args, clock=self.clock)

    def test_existing_journal_cannot_be_resumed(self):
        with self.assertRaises(FileExistsError):
            Journal(self.path)

    def test_no_update_wait_is_checked_in_chunks(self):
        trial = next(t for t in schedule() if t["arm"] == "no_update")
        self.assertTrue(self.runner.collect([trial]))
        gap = next(r for r in self.rows() if r["kind"] == "probe_start")
        self.assertEqual(gap["preload_gap_seconds"], 120)

    def test_preload_failure_blocks_attached_control(self):
        parent = next(t for t in schedule() if t["arm"] == "tighten700" and t["repeat"] == 1)
        child = next(t for t in schedule() if t["uses_parent_deployment"] == parent["id"])
        original = self.api.request
        def bad_preload(key, req):
            if key == parent["accounting_key"]:
                raise TimeoutError()
            return original(key, req)
        self.api.request = bad_preload
        self.assertFalse(self.runner.collect([parent, child]))
        statuses = {r["id"]: r["status"] for r in self.rows() if r["kind"] == "sequence_status"}
        self.assertEqual(statuses[parent["id"]], "truncated")
        self.assertEqual(statuses[child["id"]], "blocked")


if __name__ == "__main__":
    unittest.main()
