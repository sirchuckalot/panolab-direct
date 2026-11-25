import io
import struct
import unittest
from unittest.mock import Mock, call

from host_management import (
    HostManagementClient,
    Progress,
    RequestRejected,
    State,
    UncertainOutcome,
)


def request(opcode, correlation, body=b""):
    return struct.pack(">BBHI", 1, opcode, len(body), correlation) + body


def reply(opcode, correlation, state, offset=None, *, code=0):
    return request(
        opcode,
        correlation,
        struct.pack(">BBBBI", 0, code, state, int(offset is not None), offset or 0),
    )


class SimulatorReset(Exception):
    pass


class HostManagementTests(unittest.TestCase):
    begin_request = bytes.fromhex("01 01 000b 00000001 01020304 05060708 0001 a0")

    def begin(self, client):
        self.assertEqual(
            client.begin(0x01020304, 0x05060708, b"\xa0"), Progress(State.OPEN, 0)
        )

    def assert_locked(self, client, transport):
        sends = transport.call_count
        actions = (
            lambda: client.begin(1, 2, b"\xa0"),
            lambda: client.chunk(b"x"),
            lambda: client.stream(b"x"),
            client.seal,
            client.cancel,
            client.status,
        )
        for action in actions:
            with self.subTest(action=action):
                with self.assertRaises(UncertainOutcome):
                    action()
                self.assertEqual(transport.call_count, sends)

    def test_each_mutation_retries_exact_wire_bytes_after_lost_reply(self):
        for finish_name, finish_opcode, finish_state, finish_offset in (
            ("seal", 3, State.SEALED, 3),
            ("cancel", 4, State.CANCELLED, None),
        ):
            with self.subTest(finish=finish_name):
                transport = Mock(side_effect=[
                    TimeoutError("begin applied, reply lost"),
                    reply(1, 1, 2, 0),
                    TimeoutError("chunk applied, reply lost"),
                    reply(2, 2, 2, 3),
                    TimeoutError("finish applied, reply lost"),
                    reply(finish_opcode, 3, finish_state, finish_offset),
                    reply(5, 4, finish_state, finish_offset),
                ])
                client = HostManagementClient(transport)
                self.begin(client)
                self.assertEqual(client.chunk(b"\x00\xffA"), Progress(State.OPEN, 3))
                expected = Progress(finish_state, finish_offset)
                self.assertEqual(getattr(client, finish_name)(), expected)
                self.assertEqual(client.status(), expected)
                chunk_request = bytes.fromhex(
                    "01 02 000d 00000002 01020304 00000000 0003 00ff41"
                )
                finish_request = bytes.fromhex(
                    f"01 {finish_opcode:02x} 0004 00000003 01020304"
                )
                self.assertEqual(transport.call_args_list, [
                    call(self.begin_request), call(self.begin_request),
                    call(chunk_request), call(chunk_request),
                    call(finish_request), call(finish_request),
                    call(bytes.fromhex("01 05 0000 00000004")),
                ])

    def test_wrong_response_fields_lock_client_without_retry(self):
        valid = reply(1, 1, 2, 0)
        for name, invalid in (
            ("type", bytearray(valid)),
            ("short", valid[:-1]),
            ("long", valid + b"\x00"),
            ("version", b"\x02" + valid[1:]),
            ("opcode", reply(2, 1, 2, 0)),
            ("declared length", valid[:3] + b"\x07" + valid[4:]),
            ("correlation", reply(1, 2, 2, 0)),
            ("reserved", valid[:8] + b"\x01" + valid[9:]),
            ("code", reply(1, 1, 2, 0, code=9)),
            ("unknown state", reply(1, 1, 99, 0)),
            ("wrong state", reply(1, 1, 3, 0)),
            ("presence flag", valid[:11] + b"\x02" + valid[12:]),
            ("offset without flag", reply(1, 1, 2)[:-1] + b"\x01"),
            ("missing offset", reply(1, 1, 2)),
            ("wrong offset", reply(1, 1, 2, 1)),
        ):
            with self.subTest(field=name):
                transport = Mock(return_value=invalid)
                client = HostManagementClient(transport)
                with self.assertRaises(UncertainOutcome):
                    client.begin(0x01020304, 0x05060708, b"\xa0")
                transport.assert_called_once_with(self.begin_request)
                self.assert_locked(client, transport)

    def test_stream_stops_on_wrong_acknowledged_offset(self):
        transport = Mock(side_effect=[reply(1, 1, 2, 0), reply(2, 2, 2, 1023)])
        client = HostManagementClient(transport)
        self.begin(client)
        source = io.BytesIO(b"x" * 1025)
        with self.assertRaises(UncertainOutcome):
            client.stream(source)
        self.assertEqual(source.tell(), 1024)
        self.assertEqual(transport.call_args_list, [
            call(self.begin_request),
            call(request(2, 2, struct.pack(">IIH", 0x01020304, 0, 1024) + b"x" * 1024)),
        ])
        self.assert_locked(client, transport)

    def test_timeout_retry_exhaustion(self):
        for retries in (0, 2):
            with self.subTest(retries=retries):
                timeout = TimeoutError("reply lost")
                transport = Mock(side_effect=timeout)
                client = HostManagementClient(transport, timeout_retries=retries)
                with self.assertRaises(UncertainOutcome) as error:
                    client.begin(0x01020304, 0x05060708, b"\xa0")
                self.assertIs(error.exception.__cause__, timeout)
                self.assertEqual(transport.call_args_list, [call(self.begin_request)] * (retries + 1))
                self.assert_locked(client, transport)

    def test_reset_signal_stops_retries(self):
        reset = SimulatorReset("new simulator instance")
        transport = Mock(side_effect=[TimeoutError(), reset])
        client = HostManagementClient(transport, timeout_retries=3)
        with self.assertRaises(UncertainOutcome) as error:
            client.begin(0x01020304, 0x05060708, b"\xa0")
        self.assertIs(error.exception.__cause__, reset)
        self.assertEqual(transport.call_args_list, [call(self.begin_request)] * 2)
        self.assert_locked(client, transport)

    def test_short_empty_and_long_streams(self):
        for data, chunks in (
            (b"", ()),
            (b"abc", (b"abc",)),
            (b"a" * 1024 + b"b" * 1024 + b"end", (b"a" * 1024, b"b" * 1024, b"end")),
        ):
            for use_reader in (False, True):
                with self.subTest(size=len(data), reader=use_reader):
                    offset = 0
                    requests = [call(self.begin_request)]
                    replies = [reply(1, 1, 2, 0)]
                    for correlation, chunk in enumerate(chunks, start=2):
                        body = struct.pack(">IIH", 0x01020304, offset, len(chunk)) + chunk
                        requests.append(call(request(2, correlation, body)))
                        offset += len(chunk)
                        replies.append(reply(2, correlation, 2, offset))
                    transport = Mock(side_effect=replies)
                    client = HostManagementClient(transport)
                    self.begin(client)
                    source = Mock(wraps=io.BytesIO(data)) if use_reader else data
                    self.assertEqual(client.stream(source), Progress(State.OPEN, len(data)))
                    self.assertEqual(transport.call_args_list, requests)
                    if use_reader:
                        self.assertEqual(source.read.call_args_list, [call(1024)] * (len(chunks) + 1))

    def test_status_can_follow_definite_rejection(self):
        transport = Mock(side_effect=[reply(1, 1, 0, code=2), reply(5, 2, 1)])
        client = HostManagementClient(transport)
        with self.assertRaises(RequestRejected) as error:
            client.begin(0x01020304, 0x05060708, b"\xa0")
        self.assertEqual(error.exception.code, 2)
        self.assertEqual(error.exception.progress, Progress(State.UNSPECIFIED, None))
        self.assertEqual(client.status(), Progress(State.IDLE, None))
        self.assertEqual(transport.call_args_list, [
            call(self.begin_request), call(request(5, 2)),
        ])

    def test_missing_seal_offset_is_uncertain(self):
        transport=Mock(side_effect=[reply(1,1,2,0),reply(2,2,2,3),reply(3,3,3)])
        client=HostManagementClient(transport)
        self.begin(client);client.chunk(b"abc")
        with self.assertRaises(UncertainOutcome):client.seal()
        self.assert_locked(client,transport)

    def test_local_limits(self):
        transport=Mock()
        with self.assertRaises(ValueError):HostManagementClient(transport,timeout_retries=4)
        client=HostManagementClient(transport)
        for op in (0,-1,2**32,True):
            with self.assertRaises(ValueError):client.begin(op,8,b"x")
        transport.assert_not_called()


if __name__ == "__main__":
    unittest.main()
