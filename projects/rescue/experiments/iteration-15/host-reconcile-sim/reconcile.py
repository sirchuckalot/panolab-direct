"""Simulation-only read-only reconciliation policy; no transport or writes.

Snapshot fields must come from a trusted, coherent inspector that freshly
checks the exact candidate slot's manifest AND image, and boot journal.
This is not an authentication or final wire protocol implementation.
"""
from dataclasses import dataclass
from enum import Enum

class Outcome(Enum):
    VERIFIED_STAGED = "verified-staged-not-activated"
    INTERRUPTED = "interrupted-manual-restart-required"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown-do-not-mutate"

@dataclass(frozen=True)
class Claim:
    device_id: bytes
    boot_epoch: int
    operation_id: int
    journal_sequence: int
    manifest_digest: bytes
    slot: str

@dataclass(frozen=True)
class Snapshot:
    device_id: bytes
    boot_epoch: int
    operation_id: int
    journal_sequence: int
    manifest_digest: bytes
    slot: str
    state: str
    journal_valid: bool
    confirmed_verified: bool
    candidate_verified: bool
    candidate_inactive: bool

def reconcile(claim: Claim, snapshot: Snapshot) -> Outcome:
    def valid_int(n):
        return type(n) is int and 0 < n < 2**64
    if (not isinstance(claim.device_id, bytes) or len(claim.device_id)!=16
            or not any(claim.device_id)
            or not isinstance(claim.manifest_digest, bytes) or len(claim.manifest_digest)!=32
            or claim.slot not in ("A","B")
            or not all(valid_int(n) for n in (claim.boot_epoch,claim.operation_id,claim.journal_sequence,
                                              snapshot.boot_epoch,snapshot.operation_id,snapshot.journal_sequence))
            or snapshot.boot_epoch <= claim.boot_epoch
            or snapshot.device_id != claim.device_id
            or snapshot.operation_id != claim.operation_id
            or snapshot.journal_sequence != claim.journal_sequence
            or snapshot.manifest_digest != claim.manifest_digest
            or snapshot.slot != claim.slot
            or snapshot.journal_valid is not True
            or snapshot.confirmed_verified is not True
            or snapshot.candidate_inactive is not True):
        return Outcome.UNKNOWN
    if snapshot.state == "sealed":
        return Outcome.VERIFIED_STAGED if snapshot.candidate_verified is True else Outcome.UNKNOWN
    if snapshot.state == "interrupted":
        return Outcome.INTERRUPTED
    if snapshot.state == "cancelled":
        return Outcome.CANCELLED
    return Outcome.UNKNOWN
