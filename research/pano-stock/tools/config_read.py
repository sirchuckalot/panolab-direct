#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read documented network configuration words from the verified stock G2.
Only TNP configuration reads; no register writes or session setup.
Reference ELF SHA256 bb858dc7020b6f8e4328e1ec0e0e2624a01b8cbe1eb19528c641e6b43e20cd94.
ipAddress32 0x08068232 -> cfg 0x12; subnetMask 0x08068c6e -> 0x13;
gatewayAddress 0x08068e76 -> 0x16; peerIpAddress 0x08068690 -> 0x18.
"""
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import struct
import time

IDENTITY=(0,1,4,5,6,7,16,17)
NETWORK={0x12:"device_ip",0x13:"subnet_mask",0x16:"gateway",0x18:"peer_ip"}
ALLOWED=set(IDENTITY)|set(NETWORK)

def request(address,seq,tid):
    if address not in ALLOWED:
        raise ValueError("unsupported configuration address")
    return struct.pack("!BBHIH",1,8,seq<<4,0,6)+bytes(1)+address.to_bytes(3,"big")+tid.to_bytes(2,"big")

def read(sock,address,seq,tid):
    packet=request(address,seq,tid)
    entry={"address":f"0x{address:02x}","request_hex":packet.hex(),"replies":[],"value":None}
    sock.send(packet)
    deadline=time.monotonic()+2
    for _ in range(16):
        remaining=deadline-time.monotonic()
        if remaining<=0: break
        sock.settimeout(remaining)
        try: data=sock.recv(64)
        except socket.timeout: break
        entry["replies"].append(data.hex())
        if len(data)==20 and data[:2]==b"\x01\x08" and data[8:11]==b"\x00\x0a\x20" and int.from_bytes(data[11:14],"big")==address and int.from_bytes(data[14:16],"big")==tid:
            entry["value"]=f"{int.from_bytes(data[16:20],'big'):08x}"
            break
    return entry
