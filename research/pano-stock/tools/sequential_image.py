#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Acquire a single raw Rev B image, using the qualified batching algorithm.
Only an explicitly selected, owner-verified device on a private LAN.
Requires a private inventory record and a private output directory.
No program, erase, protection or FPGA reconfiguration commands.
"""
import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import time

from batch_reader import Batch, Trace, BLOCK, WORDS, COUNT, SIZE, BATCH_WORDS
from config_read import read as config_read
from pano_discovery import decode_identity, IDENTITY_ADDRESSES
from lan_discover import checked_network

def digest(data):
    return hashlib.sha256(data).hexdigest()

def verify_identity(sock, expected):
    q=secrets.randbelow(4096)
    t=1+secrets.randbelow(65500)
    words={}
    for addr in (*IDENTITY_ADDRESSES,0x18):
        result=config_read(sock,addr,q,t)
        if result["value"] is None:
            raise RuntimeError("configuration read unconfirmed")
        words[addr]=int(result["value"],16)
        q=(q+1)%4096
        t+=1
    if words[0]!=0x08010000 or words[0x18]!=0:
        raise RuntimeError("not idle Rev B")
    actual=decode_identity(expected["ip"],words)
    if actual.mac!=expected["mac"] or actual.serial!=expected["serial"] or actual.word_1!=expected["word_1"]:
        raise RuntimeError("identity mismatch")
    return q,t

def acquire(index, expected):
    if not 0<=index<COUNT:
        raise ValueError("block outside Rev B extent")
    trace=Trace()
    data=bytearray()
    start=time.monotonic()
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.bind(("0.0.0.0",8320))
        sock.connect((expected["ip"],8321))
        q,t=verify_identity(sock,expected)
        s=Batch(sock,trace)
        s.tid=1+secrets.randbelow(65530-2*WORDS)
        try:
            if not s.open() or s.read(0)!=0x08010000 or s.read(0xff)!=0:
                raise RuntimeError("session preflight failed")
            first=index*WORDS
            for i in range(first,first+WORDS,BATCH_WORDS):
                data.extend(s.read_batch(i,min(BATCH_WORDS,first+WORDS-i)))
        finally:
            closed=s.close()
            idle=config_read(sock,0x18,q,t)["value"]=="00000000"
        if not closed or not idle:
            raise RuntimeError("session closure not confirmed")
    if len(data)!=BLOCK:
        raise RuntimeError("incomplete block")
    return bytes(data),{"block":index,"offset":index*BLOCK,"size":BLOCK,
        "sha256":digest(data),"trace_sha256":trace.digest.hexdigest(),
        "seconds":time.monotonic()-start,"peer_idle":True}

def check_checkpoint(out,records):
    size=out.seek(0,2)
    if size%BLOCK or size>SIZE or len(records)!=size//BLOCK:
        raise RuntimeError("checkpoint length mismatch; preserve for review")
    out.seek(0)
    for i,r in enumerate(records):
        if r["block"]!=i or r["offset"]!=i*BLOCK or r["size"]!=BLOCK or not r["peer_idle"] or r["sha256"]!=digest(out.read(BLOCK)):
            raise RuntimeError("checkpoint data mismatch")
    return size//BLOCK

def run(directory,expected,blocks):
    directory=directory.resolve(strict=True)
    if not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise RuntimeError("output directory must be private (0700)")
    if any((p/".git").exists() for p in (directory,*directory.parents)):
        raise RuntimeError("output must be outside a Git checkout")
    part=directory/"stock.bin.partial"
    final=directory/"stock.bin"
    logpath=directory/"acquisition.jsonl"
    binding=directory/"acquisition-identity.json"
    if final.exists():
        raise RuntimeError("final image exists; use offline audit")
    if binding.exists():
        if json.loads(binding.read_text())!=expected:
            raise RuntimeError("private identity binding differs")
    else:
        if part.exists() or logpath.exists():
            raise RuntimeError("unbound checkpoint")
        fd=os.open(binding,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"w") as f:
            json.dump(expected,f)
            f.flush()
            os.fsync(f.fileno())
    fd=os.open(part,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"r+b") as out:
        fcntl.flock(out,fcntl.LOCK_EX|fcntl.LOCK_NB)
        records=[json.loads(line) for line in logpath.read_text().splitlines()] if logpath.exists() else []
        first=check_checkpoint(out,records)
        lf=os.open(logpath,os.O_WRONLY|os.O_CREAT|os.O_APPEND|os.O_NOFOLLOW,0o600)
        with os.fdopen(lf,"a") as log:
            for index in range(first,min(COUNT,first+blocks)):
                data,r=acquire(index,expected)
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
                log.write(json.dumps(r)+"\n")
                log.flush()
                os.fsync(log.fileno())
                records.append(r)
                print(f"{index+1}/{COUNT} blocks",flush=True)
        complete=len(records)==COUNT
        if complete:
            check_checkpoint(out,records)
            out.seek(0)
            image=out.read()
            if len(image)!=SIZE:
                raise RuntimeError("final size mismatch")
            os.link(part,final)
            part.unlink()
            print(json.dumps({"bytes":SIZE,"sha256":digest(image),"complete":True}))
        else:
            print(json.dumps({"blocks":len(records),"complete":False}))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--authorized-lan",required=True)
    p.add_argument("--identity",required=True,type=Path,help="Private JSON record from inventory, physically checked")
    p.add_argument("--output-directory",required=True,type=Path)
    p.add_argument("--blocks",type=int,default=COUNT)
    p.add_argument("--confirm-owner-backup",action="store_true",required=True)
    a=p.parse_args()
    net=checked_network(a.authorized_lan)
    identity=json.loads(a.identity.read_text())
    expected={k:identity[k] for k in ("ip","board_id","mac","serial","word_1")}
    if ipaddress.IPv4Address(expected["ip"]) not in net or expected["board_id"]!=0x08010000:
        p.error("target must be an owner-confirmed Rev B in the authorized subnet")
    if not 1<=a.blocks<=COUNT:
        p.error("invalid block count")
    run(a.output_directory,expected,a.blocks)

if __name__=="__main__":
    main()
