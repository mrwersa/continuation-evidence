"""Single-process scalar accounting model, separate from the reviewed fixture.

All callers use one trusted Coordinator. Its lock serialises state changes.
Leases identify owners, not authenticated credentials. Handover tickets refer
to retained authoritative state, never to caller-supplied consumed totals.
No persistence, distributed consensus, expiry, compensation, policy-language
translation, issuer amendments or external effect execution is modelled.
"""

from dataclasses import dataclass, field
from threading import RLock
from uuid import uuid4


class Rejected(ValueError):
    """An invalid transition, distinct from a valid request denied by the bound."""


def positive(value):
    if type(value) is not int or value <= 0:
        raise Rejected('expected a positive integer')


def named(value):
    if not isinstance(value, str) or not value:
        raise Rejected('expected a non-empty identifier')


@dataclass(frozen=True)
class Lease:
    account: str
    principal: str
    holder: str
    generation: int
    coordinator: str


@dataclass(frozen=True)
class Ticket:
    predecessor: Lease
    nonce: str


@dataclass
class _Account:
    lease: Lease
    limit: int
    consumed: int = 0
    # Operation IDs are never reused, including after settlement or handover.
    operations: dict = field(default_factory=dict)
    pending: Ticket | None = None

    @property
    def reserved(self):
        return sum(amount for amount, settled in self.operations.values() if not settled)


class Coordinator:
    def __init__(self):
        self._identity = uuid4().hex
        self._lock = RLock()
        self._accounts = {}

    def open(self, account, principal, holder, limit=1000):
        """Trusted initial grant. An existing account can never be reopened."""
        for value in (account, principal, holder):
            named(value)
        positive(limit)
        with self._lock:
            if account in self._accounts:
                raise Rejected('account already exists')
            lease = Lease(account, principal, holder, 0, self._identity)
            self._accounts[account] = _Account(lease, limit)
            return lease

    def _current(self, lease):
        if not isinstance(lease, Lease):
            raise Rejected('invalid lease')
        state = self._accounts.get(lease.account)
        if state is None or state.lease != lease or state.pending is not None:
            raise Rejected('not the active owner')
        return state

    def reserve(self, lease, operation, amount):
        """Reserve before work begins, enforcing consumed + reserved < limit."""
        named(operation)
        positive(amount)
        with self._lock:
            state = self._current(lease)
            if operation in state.operations:
                raise Rejected('operation already admitted')
            if state.consumed + state.reserved + amount >= state.limit:
                return 'deny'
            state.operations[operation] = (amount, False)
            return 'allow'

    def settle(self, account, principal, operation):
        """Trusted completion of exactly the reserved amount, also after close.

        Completion is tied to the admitted operation, not the current owner.
        Thus old work can settle during or after handover without new admission.
        """
        with self._lock:
            state = self._accounts.get(account)
            if state is None or principal != state.lease.principal:
                raise Rejected('unknown account or principal')
            if operation not in state.operations:
                raise Rejected('unknown reservation')
            amount, settled = state.operations[operation]
            if settled:
                return 'already-settled'
            state.operations[operation] = (amount, True)
            state.consumed += amount
            return 'settled'

    def admit(self, lease, operation, amount):
        """Convenience path for immediately completed work."""
        with self._lock:
            outcome = self.reserve(lease, operation, amount)
            if outcome == 'allow':
                self.settle(lease.account, lease.principal, operation)
            return outcome

    def close(self, lease):
        """Freeze admissions and issue exactly one reference to retained state."""
        with self._lock:
            state = self._current(lease)
            ticket = Ticket(lease, uuid4().hex)
            state.pending = ticket
            return ticket

    def accept(self, ticket, holder, limit):
        """One successor takes ownership without importing or replacing totals."""
        named(holder)
        positive(limit)
        with self._lock:
            if not isinstance(ticket, Ticket) or not isinstance(ticket.predecessor, Lease):
                raise Rejected('invalid ticket')
            old = ticket.predecessor
            state = self._accounts.get(old.account)
            if state is None or state.pending != ticket or state.lease != old:
                raise Rejected('ticket is not the outstanding handover')
            if limit > state.limit:
                raise Rejected('requires a non-widening limit')
            lease = Lease(old.account, old.principal, holder, old.generation + 1, self._identity)
            state.lease = lease
            state.limit = limit
            state.pending = None
            return lease

    def snapshot(self, account):
        """Immutable inspection value for tests, not a public import format."""
        with self._lock:
            state = self._accounts[account]
            return (state.lease, state.limit, state.consumed, state.reserved,
                    tuple(sorted(state.operations.items())), state.pending)
