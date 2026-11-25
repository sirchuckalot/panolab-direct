#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Discover and identify stock G2 devices on an owner-authorized private LAN."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import socket

from lan_discover import checked_network, collect
from pano_discovery import DiscoveryCollector

class Transport:
    def __init__(self, sock):
        self.sock=sock
    def send(self,payload,peer):
        self.sock.sendto(payload,peer)
    def receive(self,timeout):
        self.sock.settimeout(timeout)
        try:return self.sock.recvfrom(64)
        except socket.timeout:return None

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--authorized-lan",required=True)
    a=p.parse_args()
    try:net=checked_network(a.authorized_lan)
    except ValueError as e:p.error(str(e))
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
        s.bind(("0.0.0.0",8320))
        discovery=collect(s,[str(ip) for ip in net.hosts()],net)
        collector=DiscoveryCollector(Transport(s))
        identities=[]
        for candidate in discovery["candidates"]:
            identities.extend(asdict(i) for i in collector.discover([candidate["ip"]],timeout=3))
    report={"discovery":discovery,"identities":identities,
            "limitations":"G2 B/C candidates only; private authorized subnet; read-only; no authentication"}
    print(json.dumps(report,indent=2))

if __name__=="__main__":main()
