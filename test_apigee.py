"""Mutation checks over the released projection. No provider calls."""
import copy
import json
from pathlib import Path
import unittest
from verify_apigee import analyse

ROOT = Path(__file__).resolve().parent


class ApigeeTests(unittest.TestCase):
    def setUp(self):
        self.protocol, self.records, self.policies = [json.loads((ROOT/n).read_text()) for n in
            ('apigee_protocol.json', 'apigee_records.json', 'apigee_policies.json')]

    def result(self):
        return analyse(self.protocol, self.records, self.policies)

    def test_capture_counts_and_scope_result(self):
        result = self.result()
        self.assertEqual(result['statuses'], {'complete': 90})
        self.assertEqual(result['tool_calls'], 365)
        self.assertEqual(result['tool_outcomes'], {'A': 263, 'R': 102})
        self.assertEqual(result['backend_records'], 265)
        self.assertEqual(result['ready_revisions'], 110)
        self.assertEqual(result['arms']['rename_policy']['patterns'], {'A, A': 10})
        self.assertEqual(result['arms']['tighten700']['used'], {'650, 650': 20})
        self.assertEqual(result['arms']['tighten500']['requests'], {'1, 50': 10})

    def test_duplicate_backend_is_rejected(self):
        self.records['backend'].append(copy.deepcopy(self.records['backend'][0]))
        with self.assertRaises(AssertionError):
            self.result()

    def test_missing_response_is_rejected(self):
        self.records['remote_responses'].pop()
        with self.assertRaises(AssertionError):
            self.result()

    def test_wrong_receipt_is_rejected(self):
        for side in ('remote_responses', 'client_responses'):
            next(r for r in self.records[side] if 'receipt' in r)['receipt']['amount'] += 1
        with self.assertRaises(AssertionError):
            self.result()

    def test_incomplete_sequence_cannot_pass_as_complete_run(self):
        self.records['statuses'][-1]['status'] = 'truncated'
        with self.assertRaises(AssertionError):
            self.result()

    def test_unrelated_policy_change_is_rejected(self):
        q = 'apiproxy/policies/RefundQuota.xml'
        self.policies['tighten700'][q] = self.policies['tighten700'][q].replace('700', '701')
        with self.assertRaises(AssertionError):
            self.result()

    def test_wrong_revision_is_rejected(self):
        for side in ('remote_responses', 'client_responses'):
            next(r for r in self.records[side] if 'receipt' in r)['headers']['x-smoke-revision'] = 'unobserved'
        with self.assertRaises((AssertionError, KeyError)):
            self.result()

    def test_projection_has_no_deployment_identity(self):
        import re
        for filename in ('apigee_protocol.json', 'apigee_records.json', 'apigee_policies.json'):
            text = (ROOT/filename).read_text()
            self.assertIsNone(re.search(r'https?://(?!backend\.invalid)[^\s"<>]+|/home/|/tmp/|Bearer |PRIVATE KEY', text))

    def test_wrong_arm_limit_is_rejected(self):
        call = next(r for r in self.records['calls'] if r['stage'].endswith('/probe-1'))
        for side in ('remote_responses', 'client_responses'):
            next(r for r in self.records[side] if r['id'] == call['request']['id'])['headers']['x-smoke-limit'] = '999'
        with self.assertRaises(AssertionError):
            self.result()

    def test_reordered_statuses_are_rejected(self):
        self.records['statuses'][0], self.records['statuses'][1] = self.records['statuses'][1], self.records['statuses'][0]
        with self.assertRaises(AssertionError):
            self.result()

    def test_boundary_calibration_is_checked(self):
        call = next(r for r in self.records['calls'] if r['stage'] == 'equality_observation')
        for side in ('remote_responses', 'client_responses'):
            next(r for r in self.records[side] if r['id'] == call['request']['id'])['headers']['x-smoke-used'] = '999'
        with self.assertRaises(AssertionError):
            self.result()

    def test_missing_transport_response_is_rejected(self):
        self.records['remote_transport'].pop()
        with self.assertRaises(AssertionError):
            self.result()

    def test_changed_transport_response_is_rejected(self):
        self.records['remote_transport'][0]['status'] = 500
        with self.assertRaises(AssertionError):
            self.result()

    def test_refusal_cannot_dispatch_to_backend(self):
        rid = next(r['id'] for r in self.records['remote_responses'] if r.get('fault'))
        call = next(r for r in self.records['calls'] if r['request']['id'] == rid)
        self.records['backend'].append({'utc': call['utc'], 'request': call['request']})
        with self.assertRaises(AssertionError):
            self.result()

    def test_complete_status_cannot_hide_missing_sequences(self):
        self.records['statuses'].pop()
        with self.assertRaises(AssertionError):
            self.result()

    def test_complete_run_cannot_claim_technical_abort(self):
        self.records['abort'].append({'reason': 'unexpected'})
        with self.assertRaises(AssertionError):
            self.result()


if __name__ == '__main__':
    unittest.main()
