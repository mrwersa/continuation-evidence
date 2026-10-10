"""Positive and adversarial checks of the single-process coordinator."""

import itertools
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

from coordinator_model import Coordinator, Rejected
from compare_recovery import probe


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.c = Coordinator()
        self.old = self.c.open('m', 'p', 'old')
        self.assertEqual(self.c.admit(self.old, 'initial', 600), 'allow')

    def unchanged_rejection(self, function, *args):
        before = self.c.snapshot('m')
        with self.assertRaises(Rejected):
            function(*args)
        self.assertEqual(self.c.snapshot('m'), before)

    def test_carry_preserves_useful_allowance_and_strict_boundary(self):
        new = self.c.accept(self.c.close(self.old), 'new', 1000)
        self.assertEqual(self.c.admit(new, 'at-bound', 400), 'deny')
        self.assertEqual(self.c.admit(new, 'useful', 300), 'allow')
        self.assertEqual(self.c.admit(new, 'again', 100), 'deny')

    def test_two_successors_cannot_duplicate_allowance(self):
        ticket = self.c.close(self.old)
        new = self.c.accept(ticket, 'new-a', 1000)
        self.assertEqual(self.c.admit(new, 'first', 300), 'allow')
        self.unchanged_rejection(self.c.accept, ticket, 'new-b', 1000)
        self.assertEqual(self.c.admit(new, 'second', 300), 'deny')
        self.assertEqual(self.c.snapshot('m')[2], 900)

    def test_closed_predecessor_cannot_close_admit_or_reserve(self):
        self.c.close(self.old)
        self.unchanged_rejection(self.c.close, self.old)
        self.unchanged_rejection(self.c.admit, self.old, 'late', 1)
        self.unchanged_rejection(self.c.reserve, self.old, 'late', 1)

    def test_stale_ticket_fresh_nonce_does_not_replace_consumption(self):
        ticket = self.c.close(self.old)
        new = self.c.accept(ticket, 'new', 1000)
        self.c.admit(new, 'later', 300)
        self.unchanged_rejection(self.c.accept, replace(ticket, nonce='fresh'), 'other', 1000)
        self.unchanged_rejection(self.c.accept, ticket, 'other', 1000)

    def test_reservation_survives_handover_and_settles_once(self):
        self.assertEqual(self.c.reserve(self.old, 'pending', 300), 'allow')
        new = self.c.accept(self.c.close(self.old), 'new', 1000)
        self.assertEqual(self.c.snapshot('m')[2:4], (600, 300))
        self.assertEqual(self.c.admit(new, 'too-much', 100), 'deny')
        self.assertEqual(self.c.settle('m', 'p', 'pending'), 'settled')
        self.assertEqual(self.c.snapshot('m')[2:4], (900, 0))
        before = self.c.snapshot('m')
        self.assertEqual(self.c.settle('m', 'p', 'pending'), 'already-settled')
        self.assertEqual(self.c.snapshot('m'), before)
        self.assertEqual(self.c.admit(new, 'still-too-much', 100), 'deny')
        self.assertEqual(self.c.admit(new, 'remaining', 99), 'allow')

    def test_settlement_between_close_and_accept_is_retained(self):
        self.c.reserve(self.old, 'pending', 300)
        ticket = self.c.close(self.old)
        self.c.settle('m', 'p', 'pending')
        new = self.c.accept(ticket, 'new', 1000)
        self.assertEqual(self.c.snapshot('m')[2:4], (900, 0))
        self.assertEqual(self.c.admit(new, 'request', 100), 'deny')

    def test_invalid_ticket_fields_and_foreign_coordinator(self):
        ticket = self.c.close(self.old)
        for old in (replace(self.old, principal='other'), replace(self.old, generation=9),
                    replace(self.old, account='other'), replace(self.old, holder='other')):
            self.unchanged_rejection(self.c.accept, replace(ticket, predecessor=old), 'new', 1000)
        other = Coordinator()
        other_old = other.open('m', 'p', 'old')
        self.unchanged_rejection(self.c.accept, other.close(other_old), 'new', 1000)

    def test_widening_is_rejected_but_same_holder_gets_a_new_generation(self):
        ticket = self.c.close(self.old)
        self.unchanged_rejection(self.c.accept, ticket, 'new', 1001)
        new = self.c.accept(ticket, 'old', 700)
        self.assertEqual(new.holder, self.old.holder)
        self.assertEqual(new.generation, self.old.generation + 1)
        self.unchanged_rejection(self.c.admit, self.old, 'old-generation', 1)
        self.unchanged_rejection(self.c.reserve, self.old, 'old-reservation', 1)
        self.unchanged_rejection(self.c.close, self.old)
        self.assertEqual(self.c.admit(new, 'tight-bound', 100), 'deny')
        self.assertEqual(self.c.admit(new, 'tight-allow', 99), 'allow')

    def test_no_reopen_or_operation_reuse_or_unknown_settlement(self):
        self.unchanged_rejection(self.c.open, 'm', 'p', 'other', 1000)
        self.unchanged_rejection(self.c.reserve, self.old, 'initial', 1)
        self.unchanged_rejection(self.c.settle, 'm', 'wrong-principal', 'initial')
        self.unchanged_rejection(self.c.settle, 'm', 'p', 'unknown')

    def test_invalid_amounts_leave_state_unchanged(self):
        for amount in (-1, 0, True, 1.5, '1', None):
            self.unchanged_rejection(self.c.reserve, self.old, 'invalid', amount)

    def test_multiple_generations_cannot_revive_an_old_owner(self):
        first = self.c.close(self.old)
        new = self.c.accept(first, 'new', 1000)
        newest = self.c.accept(self.c.close(new), 'old', 1000)
        self.unchanged_rejection(self.c.admit, self.old, 'stale', 1)
        self.unchanged_rejection(self.c.accept, first, 'third', 1000)
        self.assertEqual(self.c.admit(newest, 'valid', 300), 'allow')

    def test_competing_threads_obtain_one_successor(self):
        ticket = self.c.close(self.old)
        barrier = Barrier(2)
        def attempt(holder):
            barrier.wait(timeout=5)
            try:
                return self.c.accept(ticket, holder, 1000)
            except Rejected:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, ['a', 'b']))
        self.assertEqual(sum(x is not None for x in outcomes), 1)

    def test_competing_reservations_share_one_bound(self):
        barrier = Barrier(2)
        def attempt(operation):
            barrier.wait(timeout=5)
            return self.c.reserve(self.old, operation, 300)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, ['a', 'b']))
        self.assertEqual(sorted(outcomes), ['allow', 'deny'])
        self.assertEqual(self.c.snapshot('m')[2:4], (600, 300))

    def test_competing_completions_settle_one_reservation_once(self):
        self.c.reserve(self.old, 'pending', 300)
        self.c.accept(self.c.close(self.old), 'new', 1000)
        barrier = Barrier(2)
        def attempt(_):
            barrier.wait(timeout=5)
            return self.c.settle('m', 'p', 'pending')
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, range(2)))
        self.assertEqual(sorted(outcomes), ['already-settled', 'settled'])
        self.assertEqual(self.c.snapshot('m')[2:4], (900, 0))

    def test_tightening_below_existing_commitments_preserves_them(self):
        self.c.reserve(self.old, 'pending', 300)
        new = self.c.accept(self.c.close(self.old), 'new', 700)
        self.assertEqual(self.c.snapshot('m')[2:4], (600, 300))
        self.assertEqual(self.c.admit(new, 'later', 1), 'deny')
        self.c.settle('m', 'p', 'pending')
        self.assertEqual(self.c.snapshot('m')[2:4], (900, 0))
        self.assertEqual(self.c.admit(new, 'after-settle', 1), 'deny')

    def test_bounded_orderings_of_close_reserve_settle_and_accept(self):
        # Reserve late work under the old lease. Its admission depends on whether
        # close happened first. Existing work must settle in either ordering.
        for ordering in itertools.permutations(('close', 'accept', 'reserve', 'settle')):
            if ordering.index('accept') < ordering.index('close'):
                continue
            c = Coordinator()
            old = c.open('m', 'p', 'old')
            c.admit(old, 'initial', 600)
            c.reserve(old, 'pending', 100)
            ticket = new = None
            for event in ordering:
                if event == 'close':
                    ticket = c.close(old)
                elif event == 'accept':
                    new = c.accept(ticket, 'new', 1000)
                elif event == 'settle':
                    c.settle('m', 'p', 'pending')
                elif ordering.index('reserve') < ordering.index('close'):
                    self.assertEqual(c.reserve(old, 'late', 200), 'allow')
                else:
                    with self.assertRaises(Rejected):
                        c.reserve(old, 'late', 200)
                self.assertLess(sum(c.snapshot('m')[2:4]), 1000)
            self.assertEqual(c.snapshot('m')[0], new)
            self.assertEqual(c.snapshot('m')[2], 700)

    def test_three_recovery_strategies_have_distinct_safety_and_usefulness(self):
        expected = {
            'Refuse': [(False, 600), (False, 600)],
            'Fresh recovery': [(True, 900), (True, 1200)],
            'Carry': [(True, 900), (False, 600)],
        }
        for strategy, values in expected.items():
            for amount, (admitted, total) in zip((300, 600), values):
                self.assertEqual(probe(strategy, amount),
                                 {'admitted': admitted, 'mandate_total': total})


if __name__ == '__main__':
    unittest.main()
