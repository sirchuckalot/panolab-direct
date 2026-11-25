#!/usr/bin/env python3
"""Lab-only read-only client. No auto-discovery, no mutation commands."""
import argparse
import ipaddress
import json
import re
import secrets
import socket

PORT=49152
MAX_RESPONSE=160
FIXED={"api_version":"1","mode":"recovery-only","paired":"false","identity_valid":"false","journal_valid":"false","warning":"LAB ONLY"}

def request_bytes(request_id):
    if not re.fullmatch(r"[0-9A-F]{8}", request_id):
        raise ValueError("invalid request ID")
    return ("RESCUE1 "+request_id).encode("ascii")

def parse_reply(data, request_id):
    request_bytes(request_id)
    if not 1<=len(data)<=MAX_RESPONSE or not data.endswith(b"\n"):
        raise ValueError("invalid response length or framing")
    result={}
    for line in data.decode("ascii").split("\n")[:-1]:
        key,sep,value=line.partition("=")
        if not sep or key in result:
            raise ValueError("invalid or duplicate field")
        result[key]=value
    if set(result)!=set(FIXED)|{"request_id","flash_probe"}:
        raise ValueError("unexpected fields")
    if any(result[k]!=v for k,v in FIXED.items()) or result["request_id"]!=request_id or result["flash_probe"] not in ("ok","failed"):
        raise ValueError("unexpected diagnostic status or request ID")
    return result

def query(ip, timeout=2.0, socket_factory=socket.socket):
    addr=ipaddress.IPv4Address(ip)
    allowed=("10.0.0.0/8","172.16.0.0/12","192.168.0.0/16","169.254.0.0/16")
    if not any(addr in ipaddress.IPv4Network(net) for net in allowed) or int(addr)&255 in (0,255):
        raise ValueError("use an explicit isolated-LAN IPv4 unicast address")
    if not 0.1<=timeout<=10:
        raise ValueError("timeout must be 0.1-10 seconds")
    rid=secrets.token_hex(4).upper()
    with socket_factory(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        s.connect((str(addr),PORT))
        s.sendall(request_bytes(rid))
        return parse_reply(s.recv(MAX_RESPONSE+1),rid)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("ip")
    p.add_argument("--isolated-lab",action="store_true",required=True,help="confirm isolated lab network and authorized diagnostic target")
    p.add_argument("--timeout",type=float,default=2)
    a=p.parse_args()
    try: print(json.dumps(query(a.ip,a.timeout),indent=2))
    except (ValueError,OSError) as e: p.exit(1,f"diagnostic failed: {e}\n")

if __name__=="__main__":
    main()
