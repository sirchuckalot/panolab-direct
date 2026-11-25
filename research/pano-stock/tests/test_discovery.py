# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from collections import deque
from ipaddress import IPv4Network
import pano_discovery as p
import lan_discover as d

WORDS={0:0x08010000,1:0x08010014,4:0x54534554,5:0x49524553,6:0x30304c41,7:0x34333231,16:0x0200,17:0x00000001}

def response(address,tid,value):
    return bytes.fromhex("0108000000000000000a20")+address.to_bytes(3,"big")+tid.to_bytes(2,"big")+value.to_bytes(4,"big")

class Fake:
    def __init__(self):
        self.queue=deque()
        self.time=0.
        self.sent=[]
    def send(self,data,peer):
        assert len(data)==16 and data[:2]==b"\x01\x08" and data[8:11]==b"\x00\x06\x00"
        a=int.from_bytes(data[11:14],"big")
        t=int.from_bytes(data[14:16],"big")
        assert a in p.IDENTITY_ADDRESSES
        self.sent.append((peer,a,t))
        if peer[0]=="192.168.50.10":return
        v=WORDS[a]
        if a==0 and peer[0]=="192.168.50.12":v=0x08010002
        if a==0 and peer[0]=="192.168.50.13":v=0x99999999
        packet=response(a,t,v)
        self.queue.extend([(b"\x01\x48"+bytes(6),peer),(packet,("192.168.50.99",8321)),(packet,(peer[0],8320)),(packet[:-1],peer),(packet,peer),(packet,peer)])
    def receive(self,timeout):
        if self.queue:
            self.time+=0.0001
            return self.queue.popleft()
        self.time+=timeout
        return None

class Tests(unittest.TestCase):
    def test_measured_packet(self):
        self.assertEqual(p._read_response(bytes.fromhex("0108000000000000000a20000000000108010000")),(0,1,0x08010000))
        self.assertEqual(p._read_request(0,1).hex(),"01080010000000000006000000000001")
    def test_multiple_and_noise(self):
        f=Fake()
        c=p.DiscoveryCollector(f,clock=lambda:f.time)
        identities=c.discover(["192.168.50.10","192.168.50.11","192.168.50.12","192.168.50.13","192.168.50.11"])
        self.assertEqual([i.model for i in identities],["G2 B","G2 C"])
        self.assertEqual(identities[0].serial,"TESTSERIAL001234")
        self.assertEqual(identities[0].mac,"02:00:00:00:00:01")
        self.assertEqual(len([x for x in f.sent if x[0][0]=="192.168.50.13"]),1)
        self.assertEqual(len({x[2] for x in f.sent}),len(f.sent))
    def test_bounds(self):
        for n in ("8.8.8.0/24","192.168.0.0/16","192.168.50.175/24"):
            with self.assertRaises(ValueError):d.checked_network(n)
        with self.assertRaises(ValueError):p._read_request(0x5000,1)
    def test_malformed(self):
        packet=response(0,1,0x08010000)
        for i in range(len(packet)):
            self.assertIsNone(p._read_response(packet[:i]))
        self.assertIsNone(p._read_response(packet+b"\x00"))
    def test_sender_correlation(self):
        hits={}; net=IPv4Network("192.168.50.0/24"); pending={1:"192.168.50.11"}
        packet=response(0,1,0x08010000)
        d.accept(packet,"192.168.50.12",8321,pending,hits,net,False)
        d.accept(packet,"192.168.50.11",8320,pending,hits,net,False)
        self.assertFalse(hits)
        d.accept(packet,"192.168.50.11",8321,pending,hits,net,False)
        d.accept(packet,"192.168.50.11",8321,pending,hits,net,False)
        self.assertEqual(len(hits),1)
    def test_timeout(self):
        f=Fake()
        self.assertEqual(p.DiscoveryCollector(f,clock=lambda:f.time).discover(["192.168.50.10"],timeout=.5),[])
        self.assertAlmostEqual(f.time,.5)

if __name__=="__main__":unittest.main()
