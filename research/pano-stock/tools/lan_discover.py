#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, read-only stock Pano G2 discovery on an explicitly selected LAN.

No privileged sockets, no host networking, no programming, no arbitrary
registers or service scanning. Only the vendor board-ID discovery request
is sent, on UDP 8321. The owner must authorize the LAN. Results are candidate
identities, not authentication.
"""
import argparse
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import time

from pano_discovery import _read_request, _read_response, BOARD_MODELS

PRIVATE = tuple(map(ipaddress.IPv4Network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))

def checked_network(value):
    network = ipaddress.IPv4Network(value, strict=True)
    if not any(network.subnet_of(p) for p in PRIVATE) or network.num_addresses > 256:
        raise ValueError("Specify an authorized RFC1918 subnet of /24 or smaller")
    return network

def collect(sock, targets, network, *, broadcast=False, clock=time.monotonic):
    pending = {}
    hits = {}
    start = clock()
    transaction = 1+secrets.randbelow(65000)
    for target in targets:
        pending[transaction] = target
        sock.sendto(_read_request(0, transaction), (target, 8321))
        transaction += 1
        # Slow discovery only, with a short bounded receive window after each send.
        deadline = clock()+0.05
        if broadcast:
            deadline = clock()+2.0
        for _ in range(32):
            remaining=deadline-clock()
            if remaining<=0:
                break
            sock.settimeout(remaining)
            try:
                data, (peer, port)=sock.recvfrom(64)
            except socket.timeout:
                break
            except ConnectionRefusedError:
                continue
            accept(data, peer, port, pending, hits, network, broadcast)
    # Collect delayed responses, bounded in time and packet count.
    deadline = clock()+2.0
    for _ in range(512):
        remaining=deadline-clock()
        if remaining<=0:
            break
        sock.settimeout(remaining)
        try:
            data,(peer,port)=sock.recvfrom(64)
        except socket.timeout:
            break
        except ConnectionRefusedError:
            continue
        accept(data, peer, port, pending, hits, network, broadcast)
    return {"method":"broadcast" if broadcast else "directed",
            "subnet":str(network),"requests":len(pending),
            "elapsed_seconds":round(clock()-start,3),
            "candidates":sorted(hits.values(),key=lambda r: ipaddress.IPv4Address(r["ip"]))}

def accept(data, peer, port, pending, hits, network, broadcast):
    if port!=8321 or ipaddress.IPv4Address(peer) not in network:
        return
    parsed=_read_response(data)
    if parsed is None:
        return
    address, transaction, board=parsed
    if address!=0 or board not in BOARD_MODELS or transaction not in pending:
        return
    if not broadcast and pending[transaction]!=peer:
        return
    hits[peer]={"ip":peer,"board_id":f"0x{board:08x}","model":BOARD_MODELS[board]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--authorized-lan", required=True)
    p.add_argument("--method", choices=("broadcast","directed"), default="broadcast")
    a=p.parse_args()
    try:
        net=checked_network(a.authorized_lan)
    except ValueError as e:
        p.error(str(e))
    broadcast=a.method=="broadcast"
    targets=[str(net.broadcast_address)] if broadcast else [str(ip) for ip in net.hosts()]
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.bind(("0.0.0.0",8320))
        if broadcast:
            s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        result=collect(s,targets,net,broadcast=broadcast)
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
