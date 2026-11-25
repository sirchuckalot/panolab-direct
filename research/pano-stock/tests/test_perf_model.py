# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from perf_model import parse_read_responses,stop_and_wait_throughput,batched_throughput

def frame(tid,word,address=0x5000):
    return bytes.fromhex("000a50")+address.to_bytes(3,"big")+tid.to_bytes(2,"big")+word.to_bytes(4,"big")
class Tests(unittest.TestCase):
    def test_multiple(self):
        x=parse_read_responses(frame(3,123)+frame(4,456),{3:0x5000,4:0x5000})
        self.assertEqual([r.value for r in x],[123,456])
    def test_duplicate(self):
        with self.assertRaises(ValueError):parse_read_responses(frame(3,1)*2,{3:0x5000})
    def test_missing(self):
        with self.assertRaises(ValueError):parse_read_responses(frame(3,1),{3:0x5000,4:0x5000})
    def test_wrong_address(self):
        with self.assertRaises(ValueError):parse_read_responses(frame(3,1,0x5001),{3:0x5000})
    def test_unknown_id(self):
        with self.assertRaises(ValueError):parse_read_responses(frame(4,1),{3:0x5000})
    def test_truncation(self):
        for i in range(12):
            with self.assertRaises(ValueError):parse_read_responses(frame(3,1)[:i],{3:0x5000})
    def test_model(self):
        self.assertEqual(stop_and_wait_throughput(),2000)
        self.assertEqual(batched_throughput(72),288000)
if __name__=="__main__":unittest.main()
