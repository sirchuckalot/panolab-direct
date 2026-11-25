# SPDX-License-Identifier: GPL-3.0-or-later
"""Synthetic, offline tests. No captured device identities or sockets."""
import io
import unittest
from unittest.mock import patch
from framing import header, decode
from stream_status import Session
from sequential_image import check_checkpoint, digest, verify_identity, BLOCK

class FakeSocket:
    def __init__(self, replies):
        self.replies=list(replies)
        self.sent=[]
    def settimeout(self,timeout):
        pass
    def send(self,packet):
        self.sent.append(packet)
    def recv(self,size):
        import socket
        if not self.replies:
            raise socket.timeout()
        return self.replies.pop(0)

class Tests(unittest.TestCase):
    def test_header_and_wrap(self):
        self.assertEqual(decode(header(0x40,4095,0)),(0x40,4095,0,b""))
        with self.assertRaises(ValueError):
            header(0x40,4096)
    def test_stream_status(self):
        f=FakeSocket([bytes.fromhex("01c3000000000000"),
                      bytes.fromhex("0143001001000000000a20000000000708010000"),
                      bytes.fromhex("0143002002000000000a500000ff000800000000"),
                      bytes.fromhex("0153003000000000")])
        s=Session(f,[])
        s.tid=7
        self.assertTrue(s.open())
        self.assertEqual(s.read(0),0x08010000)
        self.assertEqual(s.read(0xff),0)
        self.assertTrue(s.close())
        self.assertFalse(f.replies)
    def test_ack_not_data(self):
        f=FakeSocket([bytes.fromhex("01c3000000000000"),bytes.fromhex("0143001001000000")])
        s=Session(f,[])
        self.assertTrue(s.open())
        self.assertIsNone(s.read(0))
    def test_wrong_register(self):
        s=Session(FakeSocket([]),[])
        with self.assertRaises(ValueError):
            s.read(0x5001)
    def test_checkpoint(self):
        data=bytes(BLOCK)
        records=[{"block":0,"offset":0,"size":BLOCK,"peer_idle":True,"sha256":digest(data)}]
        self.assertEqual(check_checkpoint(io.BytesIO(data),records),1)
        with self.assertRaises(RuntimeError):
            check_checkpoint(io.BytesIO(data[:-1]),records)
        with self.assertRaises(RuntimeError):
            check_checkpoint(io.BytesIO(b"X"+data[1:]),records)
        with self.assertRaises(RuntimeError):
            check_checkpoint(io.BytesIO(data),[])
    def test_identity_gate(self):
        expected={"ip":"192.168.50.10","mac":"02:00:00:00:00:01","serial":"TESTSERIAL001234","word_1":0x08010014}
        words={0:0x08010000,1:0x08010014,4:0x54534554,5:0x49524553,6:0x30304c41,7:0x34333231,16:0x0200,17:1,0x18:0}
        def read(sock,address,seq,tid):
            return {"value":f"{words[address]:08x}"}
        with patch("sequential_image.config_read",read):
            verify_identity(None,expected)
            words[0x18]=1
            with self.assertRaises(RuntimeError):
                verify_identity(None,expected)
            words[0x18]=0
            words[17]=2
            with self.assertRaises(RuntimeError):
                verify_identity(None,expected)
if __name__=="__main__":
    unittest.main()
