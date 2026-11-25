# SPDX-License-Identifier: GPL-3.0-or-later
import json, secrets, socket, time
from pathlib import Path
from framing import decode,header

class Session:
    def __init__(self,sock,records):
        self.sock=sock;self.records=records;self.seq=0;self.peer_seq=None
        self.tid=1+secrets.randbelow(65530)
    def send(self,data):
        self.records.append({"tx":data.hex()});self.sock.send(data)
    def recv(self,predicate,seconds=2):
        deadline=time.monotonic()+seconds
        for _ in range(32):
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            self.sock.settimeout(remaining)
            try:data=self.sock.recv(256)
            except socket.timeout:break
            self.records.append({"rx":data.hex()})
            try:f,q,a,p=decode(data)
            except ValueError:continue
            if predicate(f,q,a,p):return f,q,a,p
        return None
    def open(self):
        self.send(header(0x80,0))
        r=self.recv(lambda f,q,a,p:f in (0xc0,0xc3) and a==0 and not p)
        if not r:return False
        self.peer_seq=r[1];self.seq=1
        self.send(header(0x40,self.seq,self.peer_seq))
        return True
    def read(self,address):
        if address not in (0,0xff):raise ValueError("read outside diagnostic allowlist")
        if self.peer_seq is None:raise RuntimeError("no session")
        op=0 if address==0 else 0x30
        reply_op=0x20 if address==0 else 0x50
        prefix=bytes([reply_op])+address.to_bytes(3,"big")+self.tid.to_bytes(2,"big")
        body=b"\x00\x06"+bytes([op])+address.to_bytes(3,"big")+self.tid.to_bytes(2,"big")
        self.send(header(0x40,self.seq,self.peer_seq)+body)
        r=self.recv(lambda f,q,a,p:f in (0x40,0x43) and a==self.seq and q==(self.peer_seq+1)%4096 and len(p)==12 and p[:2]==b"\x00\x0a" and p[2:8]==prefix)
        self.seq=(self.seq+1)%4096;self.tid+=1
        if r is None:return None
        self.peer_seq=r[1]
        self.send(header(0x40,self.seq,self.peer_seq))
        return int.from_bytes(r[3][8:12],"big")
    def close(self):
        if self.peer_seq is None:return False
        # Documented transport close, no endpoint message.
        packet=b"\x01\x10"+((self.seq<<12)|self.peer_seq).to_bytes(3,"big")+bytes(3)
        self.send(packet)
        r=self.recv(lambda f,q,a,p:f in (0x50,0x53) and not p,seconds=1)
        self.peer_seq=None
        return r is not None
