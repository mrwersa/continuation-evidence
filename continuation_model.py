"""Executable reference model of the continuation interface in the manuscript.

The model illustrates local sequential checks, not the full single-successor
requirement. Separate instances can import the same allowance, and a fresh nonce
can allow an old total to overwrite successor consumption. test_scope.py records
these limits. HMAC stands in for the issuer signature. This is an offline
fixture, not a deployment or evidence about any live service.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass

ISSUER_KEY = b"reference-model-issuer-key"
AMOUNT = 600
LIMIT = 1000


def _sign(payload: dict[str, object]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(ISSUER_KEY, body, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Record:
    """A signed continuation record, as returned with a stale-session result."""

    accounting_id: str
    principal: str
    predecessor_revision: str
    limit: int
    consumed: int
    reserved: int
    nonce: str
    signature: str

    def payload(self) -> dict[str, object]:
        return {
            "accounting_id": self.accounting_id,
            "consumed": self.consumed,
            "limit": self.limit,
            "nonce": self.nonce,
            "predecessor_revision": self.predecessor_revision,
            "principal": self.principal,
            "reserved": self.reserved,
        }

    def valid(self) -> bool:
        return hmac.compare_digest(self.signature, _sign(self.payload()))


@dataclass(frozen=True)
class Amendment:
    """An issuer amendment naming the mandate, the new bound and the treatment."""

    accounting_id: str
    limit: int
    treatment: str
    signature: str

    def valid(self) -> bool:
        return hmac.compare_digest(
            self.signature,
            _sign(
                {
                    "accounting_id": self.accounting_id,
                    "limit": self.limit,
                    "treatment": self.treatment,
                }
            ),
        )


def amend(accounting_id: str, limit: int, treatment: str) -> Amendment:
    payload = {"accounting_id": accounting_id, "limit": limit, "treatment": treatment}
    return Amendment(accounting_id, limit, treatment, _sign(payload))


class DecisionPoint:
    """One policy revision, with consumed state keyed to the accounting identifier."""

    def __init__(self, revision: str, limit: int = LIMIT, in_flight: tuple[str, ...] = ()) -> None:
        self.revision = revision
        self.limit = limit
        self.consumed: dict[str, int] = {}
        self.reserved: dict[str, int] = {}
        self.carried: set[str] = set()
        self.closed: set[str] = set()
        self.spent_nonces: set[str] = set()
        self.require = set(in_flight)

    def admit(self, accounting_id: str, revision: str, amount: int) -> str:
        """Decide one request. A predecessor revision or a closed mandate is refused."""
        if revision != self.revision:
            return "stale"
        if accounting_id in self.closed:
            return "closed"
        if accounting_id in self.require and accounting_id not in self.carried:
            return "awaiting-continuation"
        committed = self.consumed.get(accounting_id, 0) + self.reserved.get(accounting_id, 0)
        if committed + amount > self.limit:
            return "deny"
        self.consumed[accounting_id] = self.consumed.get(accounting_id, 0) + amount
        return "allow"

    def reserve(self, accounting_id: str, amount: int) -> None:
        """Record work admitted but not yet committed, which the summary must cover."""
        self.reserved[accounting_id] = self.reserved.get(accounting_id, 0) + amount

    def close(self, accounting_id: str, nonce: str) -> Record:
        """Settle the mandate here and hand out its signed summary."""
        self.closed.add(accounting_id)
        payload = {
            "accounting_id": accounting_id,
            "consumed": self.consumed.get(accounting_id, 0),
            "limit": self.limit,
            "nonce": nonce,
            "predecessor_revision": self.revision,
            "principal": "principal-a",
            "reserved": self.reserved.get(accounting_id, 0),
        }
        return Record(
            accounting_id=accounting_id,
            principal="principal-a",
            predecessor_revision=self.revision,
            limit=self.limit,
            consumed=payload["consumed"],
            reserved=payload["reserved"],
            nonce=nonce,
            signature=_sign(payload),
        )

    def accept(self, record: Record, amendment: Amendment | None = None) -> str:
        """Verify one declared outcome before any successor work is admitted."""
        if not record.valid():
            return "rejected-signature"
        if record.nonce in self.spent_nonces:
            return "rejected-replay"
        if record.predecessor_revision == self.revision:
            return "rejected-same-revision"
        if self.limit > record.limit:
            if amendment is None or not amendment.valid():
                return "rejected-widening"
            if amendment.accounting_id != record.accounting_id or amendment.limit != self.limit:
                return "rejected-amendment"
        self.spent_nonces.add(record.nonce)
        self.carried.add(record.accounting_id)
        self.consumed[record.accounting_id] = record.consumed
        self.reserved[record.accounting_id] = record.reserved
        return "carried"


def _case(name: str, observed: object, expected: object) -> None:
    if observed != expected:
        raise ValueError(f"{name}: expected {expected!r}, observed {observed!r}")
    print(f"PASS  {name}")


def main() -> None:
    mandate = "mandate-1"

    predecessor = DecisionPoint("revision-1")
    _case(
        "predecessor admits the first request",
        predecessor.admit(mandate, "revision-1", AMOUNT),
        "allow",
    )
    _case(
        "predecessor refuses the second request",
        predecessor.admit(mandate, "revision-1", AMOUNT),
        "deny",
    )

    record = predecessor.close(mandate, "nonce-1")
    successor = DecisionPoint("revision-2", in_flight=(mandate,))
    _case(
        "successor admits nothing before a declared outcome",
        successor.admit(mandate, "revision-2", AMOUNT),
        "awaiting-continuation",
    )
    _case("valid carry is accepted", successor.accept(record), "carried")
    _case(
        "carried state refuses work the predecessor would refuse",
        successor.admit(mandate, "revision-2", AMOUNT),
        "deny",
    )
    _case(
        "carried state admits what remains",
        successor.admit(mandate, "revision-2", LIMIT - AMOUNT),
        "allow",
    )
    _case("replayed record is refused", successor.accept(record), "rejected-replay")
    _case(
        "predecessor work after a successor exists is refused",
        predecessor.admit(mandate, "revision-1", AMOUNT),
        "closed",
    )

    tampered = Record(
        accounting_id=record.accounting_id,
        principal=record.principal,
        predecessor_revision=record.predecessor_revision,
        limit=record.limit,
        consumed=0,
        reserved=record.reserved,
        nonce="nonce-2",
        signature=record.signature,
    )
    _case(
        "a summary that loses consumption is refused",
        DecisionPoint("revision-3").accept(tampered),
        "rejected-signature",
    )

    widened = DecisionPoint("revision-4", limit=1200)
    carried = predecessor.close(mandate, "nonce-3")
    _case("widening without an amendment is refused", widened.accept(carried), "rejected-widening")
    _case(
        "an issuer amendment permits the wider bound",
        widened.accept(carried, amend(mandate, 1200, "carry")),
        "carried",
    )
    _case(
        "the amended bound still counts predecessor consumption",
        widened.admit(mandate, "revision-4", AMOUNT),
        "allow",
    )
    _case(
        "the amended bound refuses the request that crosses it",
        widened.admit(mandate, "revision-4", AMOUNT),
        "deny",
    )

    in_flight = "mandate-2"
    reserving = DecisionPoint("revision-5")
    _case(
        "work is admitted before any reservation",
        reserving.admit(in_flight, "revision-5", AMOUNT),
        "allow",
    )
    reserving.reserve(in_flight, 300)
    reserved_record = reserving.close(in_flight, "nonce-4")
    successor = DecisionPoint("revision-6", in_flight=(in_flight,))
    _case("the carried summary covers reserved work", successor.accept(reserved_record), "carried")
    _case(
        "reserved work still bounds the successor",
        successor.admit(in_flight, "revision-6", 200),
        "deny",
    )
    _case(
        "the successor admits only what reservation leaves",
        successor.admit(in_flight, "revision-6", 100),
        "allow",
    )


if __name__ == "__main__":
    main()
