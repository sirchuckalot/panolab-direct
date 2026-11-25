# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import hashlib
import json
import os
import secrets
import socket
import time
from pathlib import Path
from stream_status import Session, header
from perf_model import parse_read_responses
ACK_EVERY=16
BATCH_WORDS=72

BASE=0
SIZE=0x1000000
BLOCK=0x8000
WORDS=BLOCK//4
COUNT=SIZE//BLOCK

class Trace:
    def __init__(self):
        self.digest=hashlib.sha256()
        self.tx=0
        self.rx=0
    def append(self,item):
        direction,data=next(iter(item.items()))
        packet=bytes.fromhex(data)
        self.digest.update(direction.encode()+len(packet).to_bytes(2,"big")+packet)
        if direction=="tx":self.tx+=1
        else:self.rx+=1

class Batch(Session):
    def read_batch(self,first,count):
        if not 1<=count<=72 or not 0<=first<first+count<=SIZE//4 or self.peer_seq is None or self.tid+2*count>65536:
            raise ValueError("outside Rev B flash bounds")
        body=bytearray(); expected={}
        for i in range(first,first+count):
            body.extend(bytes.fromhex("000a40005001")+self.tid.to_bytes(2,"big")+(0x80000000|i).to_bytes(4,"big"))
            self.tid+=1
            body.extend(bytes.fromhex("000630005000")+self.tid.to_bytes(2,"big"))
            expected[self.tid]=0x5000
            self.tid+=1
        seq=self.seq
        self.send(header(0x40,seq,self.peer_seq)+body)
        self.seq=(seq+1)%4096
        replies={}
        packets=0
        deadline=time.monotonic()+2
        for _ in range(2*count+8):
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            self.sock.settimeout(remaining)
            try:data=self.sock.recv(1500)
            except socket.timeout:break
            self.records.append({"rx":data.hex()})
            from framing import decode
            f,q,a,p=decode(data)
            if f not in (0x40,0x43) or a!=seq:continue
            if not p:continue
            if q!=(self.peer_seq+1)%4096:raise RuntimeError("unexpected response sequence")
            if len(p)%12:raise RuntimeError("unexpected response length")
            current={int.from_bytes(p[k+6:k+8],"big"):0x5000 for k in range(0,len(p),12)}
            if any(t not in expected or t in replies for t in current):raise RuntimeError("unexpected transaction")
            for r in parse_read_responses(p,current):
                replies[r.transaction_id]=r.value.to_bytes(4,"big")
            self.peer_seq=q
            packets+=1
            if packets%ACK_EVERY==0 or len(replies)==count:self.send(header(0x40,self.seq,self.peer_seq))
            if len(replies)==count:return b"".join(replies[t] for t in expected)
        raise RuntimeError(f"incomplete batch: {len(replies)}/{count}")
