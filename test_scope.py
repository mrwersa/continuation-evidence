"""Offline examples and explicit limits of the reviewed scalar fixture.

Passing the limitation tests means the known unsafe behaviour is reproduced,
not that the full handover requirements are satisfied. No provider is called.
"""

import itertools
import unittest

from continuation_model import DecisionPoint


def scalar_allows(limit, consumed, future):
    for amount in future:
        consumed += amount
        if consumed >= limit:
            return False
    return True


def recipients_allow(seen, future, limit=2):
    seen = set(seen)
    for recipient in future:
        seen.add(recipient)
        if len(seen) > limit:
            return False
    return True


class PolicyExamples(unittest.TestCase):
    def test_scalar_sufficient_condition_bounded_enumeration(self):
        # Strict threshold, fixed units/window, non-negative amounts, no expiry.
        futures = [p for n in range(4) for p in itertools.product(range(3), repeat=n)]
        for limit in range(1, 6):
            for new_limit in range(1, limit + 1):
                for consumed in range(6):
                    for carried in range(consumed, 6):
                        for future in futures:
                            if scalar_allows(new_limit, carried, future):
                                self.assertTrue(scalar_allows(limit, consumed, future))

    def test_recipient_set_preserves_membership_and_bound(self):
        self.assertTrue(recipients_allow({'a', 'b'}, ['a']))
        self.assertFalse(recipients_allow({'a', 'b'}, ['c']))
        self.assertTrue(recipients_allow({'a'}, ['c']))

    def test_same_recipient_count_does_not_determine_permission(self):
        first, second = {'a', 'b'}, {'b', 'c'}
        self.assertEqual(len(first), len(second))
        self.assertTrue(recipients_allow(first, ['a']))
        self.assertFalse(recipients_allow(second, ['a']))


class KnownFixtureLimits(unittest.TestCase):
    def predecessor(self):
        point = DecisionPoint('old')
        self.assertEqual(point.admit('mandate', 'old', 600), 'allow')
        return point

    def test_separate_successors_duplicate_remaining_allowance(self):
        record = self.predecessor().close('mandate', 'first')
        for revision in ('new-a', 'new-b'):
            point = DecisionPoint(revision)
            self.assertEqual(point.accept(record), 'carried')
            self.assertEqual(point.admit('mandate', revision, 400), 'allow')

    def test_new_nonce_allows_stale_total_to_replace_consumption(self):
        old = self.predecessor()
        new = DecisionPoint('new')
        self.assertEqual(new.accept(old.close('mandate', 'first')), 'carried')
        self.assertEqual(new.admit('mandate', 'new', 400), 'allow')
        self.assertEqual(new.accept(old.close('mandate', 'second')), 'carried')
        self.assertEqual(new.consumed['mandate'], 600)
        self.assertEqual(new.admit('mandate', 'new', 400), 'allow')


if __name__ == '__main__':
    unittest.main()
