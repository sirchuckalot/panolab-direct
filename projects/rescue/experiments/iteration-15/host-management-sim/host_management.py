"""Client for the provisional simulation wire.

transport(request: bytes) returns one reply as bytes or raises TimeoutError.
The transport must raise a different exception if it detects a simulator reset.
After uncertainty, construct a new client bound to an explicitly new simulated
instance. The wire has no instance identifier, so silent resets are undetectable
if the new instance returns a reply identical to the expected one.
"""

import io
import struct
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from threading import Lock


_HEADER = struct.Struct(">BBHI")
_REPLY = struct.Struct(">BBBBI")
_MAX_U32 = 0xFFFFFFFF
_MAX_CHUNK = 1024


class Operation(IntEnum):
    BEGIN = 1
    CHUNK = 2
    SEAL = 3
    CANCEL = 4
    STATUS = 5


class State(IntEnum):
    UNSPECIFIED = 0
    IDLE = 1
    OPEN = 2
    SEALED = 3
    CANCELLED = 4


@dataclass(frozen=True)
class Progress:
    state: State
    next_offset: int | None


class ClientError(Exception):
    pass


class UncertainOutcome(ClientError):
    pass


class RequestRejected(ClientError):
    def __init__(self, code, progress):
        self.code = code
        self.progress = progress
        super().__init__(f"Simulator returned management code {code}")


class HostManagementClient:
    def __init__(self, transport, *, timeout_retries=1):
        if not callable(transport):
            raise TypeError("transport must be callable")
        if type(timeout_retries) is not int or not 0 <= timeout_retries <= 3:
            raise ValueError("timeout_retries must be an integer from 0 to 3")
        self._transport = transport
        self._timeout_retries = timeout_retries
        self._gate = Lock()
        self._locked = False
        self._last_id = 0
        self._last_operation = 0
        self._operation_id = None
        self._progress = None

    @contextmanager
    def _exclusive(self):
        if not self._gate.acquire(blocking=False):
            raise ClientError("Another client call is in progress")
        try:
            if self._locked:
                raise UncertainOutcome("Bind a new client to a new simulated instance")
            yield
        finally:
            self._gate.release()

    @staticmethod
    def _decode(reply, operation, correlation):
        if (not isinstance(reply, bytes) or len(reply) != 16
                or _HEADER.unpack_from(reply) != (1, operation, 8, correlation)):
            raise ValueError("Invalid reply length or header")
        reserved, code, state, present, offset = _REPLY.unpack_from(reply, 8)
        if reserved or code > 8 or present not in (0, 1) or (not present and offset):
            raise ValueError("Invalid reply body")
        if code not in (0,5) and (state or present or offset):
            raise ValueError("Unexpected progress on rejection")
        return code, Progress(State(state), offset if present else None)

    def _exchange(self, operation, body=b"", expected=None):
        if self._last_id == _MAX_U32:
            raise ClientError("Correlation IDs exhausted")
        self._last_id += 1
        correlation = self._last_id
        request = _HEADER.pack(1, operation, len(body), correlation) + body

        # Keep the client locked unless the whole exchange is resolved.
        self._locked = True
        for attempt in range(self._timeout_retries + 1):
            try:
                reply = self._transport(request)
                break
            except TimeoutError as error:
                if attempt == self._timeout_retries:
                    raise UncertainOutcome("Reply timeout budget exhausted") from error
            except Exception as error:
                raise UncertainOutcome("Transport failed during exchange") from error
        try:
            code, progress = self._decode(reply, operation, correlation)
        except ValueError as error:
            raise UncertainOutcome("Invalid management reply") from error
        if code:
            # After a timeout, a rejection can come from a reset or lost replay
            # entry. An active operation also requires its identity to stay known.
            rejection = RequestRejected(code, progress)
            if attempt or self._operation_id is not None or code == 8:
                raise UncertainOutcome("Simulator rejected an ambiguous exchange") from rejection
            self._locked = False
            raise rejection

        if expected is not None and progress != expected:
            raise UncertainOutcome(f"Expected {expected!r}, received {progress!r}")
        if operation == Operation.STATUS:
            if (progress.state == State.UNSPECIFIED
                    or (progress.state == State.OPEN and progress.next_offset is None)
                    or (progress.state in (State.IDLE, State.CANCELLED)
                        and progress.next_offset is not None)):
                raise UncertainOutcome("Invalid status progress")
        self._locked = False
        return progress

    def begin(self, operation_id, expected_sequence, manifest):
        """Begin an operation with caller-supplied canonical CBOR manifest bytes."""
        with self._exclusive():
            if self._operation_id is not None:
                raise ClientError("An operation is already open")
            if not isinstance(manifest, bytes) or not 1 <= len(manifest) <= _MAX_CHUNK:
                raise ValueError("manifest must contain 1 to 1024 bytes")
            if type(operation_id) is not int or not self._last_operation < operation_id <= _MAX_U32:
                raise ValueError("operation ID must be increasing and nonzero")
            if type(expected_sequence) is not int or not 0 <= expected_sequence <= _MAX_U32:
                raise ValueError("invalid journal sequence")
            body = struct.pack(">IIH", operation_id, expected_sequence, len(manifest))
            self._last_operation = operation_id
            self._progress = self._exchange(
                Operation.BEGIN, body + manifest, Progress(State.OPEN, 0)
            )
            self._operation_id = operation_id
            return self._progress

    def _require_open(self):
        if self._operation_id is None:
            raise ClientError("Begin an operation first")

    def _chunk(self, data):
        if not isinstance(data, bytes) or not 1 <= len(data) <= _MAX_CHUNK:
            raise ValueError("chunk must contain 1 to 1024 bytes")
        offset = self._progress.next_offset
        next_offset = offset + len(data)
        if next_offset > _MAX_U32:
            raise ValueError("image offset exceeds the wire limit")
        body = struct.pack(">IIH", self._operation_id, offset, len(data)) + data
        self._progress = self._exchange(
            Operation.CHUNK, body, Progress(State.OPEN, next_offset)
        )
        return self._progress

    def chunk(self, data):
        with self._exclusive():
            self._require_open()
            return self._chunk(data)

    def stream(self, source):
        """Send chunks from bytes or a binary reader, leaving the operation open."""
        with self._exclusive():
            self._require_open()
            reader = io.BytesIO(source) if isinstance(source, bytes) else source
            while True:
                data = reader.read(_MAX_CHUNK)
                if isinstance(data, bytes) and not data:
                    return self._progress
                self._chunk(data)

    def _finish(self, operation, expected):
        body = struct.pack(">I", self._operation_id)
        self._progress = self._exchange(operation, body, expected)
        self._operation_id = None
        return self._progress

    def seal(self):
        with self._exclusive():
            self._require_open()
            return self._finish(
                Operation.SEAL, Progress(State.SEALED, self._progress.next_offset)
            )

    def cancel(self):
        with self._exclusive():
            self._require_open()
            return self._finish(Operation.CANCEL, Progress(State.CANCELLED, None))

    def status(self):
        """Check progress without adopting a remote operation or resuming it."""
        with self._exclusive():
            return self._exchange(Operation.STATUS, expected=self._progress)
