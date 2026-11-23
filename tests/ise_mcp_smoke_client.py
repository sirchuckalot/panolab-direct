#!/usr/bin/env python3
"""Integration test of the embedded ISE worker through MCP ONLY.

Run in an approved laptop test container with private access to the MCP
endpoint. Does not use Docker, SSH, Xilinx command-line, or hardware programming.
With --run-build, requests the external example project through generic build_start.
"""
import argparse
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

TOOLS = {"toolchain_info", "build_start", "build_status", "build_result", "build_cancel"}

class MCPClient:
    def __init__(self, url, token):
        self.url = url
        self.token = token
        self.id = 0
    def rpc(self, method, params=None):
        self.id += 1
        data = json.dumps({"jsonrpc": "2.0", "id": self.id, "method": method, "params": params or {}}).encode()
        request = urllib.request.Request(
            self.url, data=data, method="POST",
            headers={"Authorization": "Bearer " + self.token,
                     "Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream",
                     "MCP-Protocol-Version": "2025-11-25"})
        with urllib.request.urlopen(request, timeout=35) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read(1024 * 1024)
        if "application/json" in content_type:
            reply = json.loads(body)
        elif "text/event-stream" in content_type:
            chunks = [line[6:].strip() for line in body.decode().splitlines() if line.startswith("data: ")]
            reply = json.loads(chunks[-1])
        else:
            raise RuntimeError("unexpected MCP content-type: " + content_type)
        if "error" in reply:
            raise RuntimeError("MCP RPC error: " + str(reply["error"]))
        return reply.get("result", {})
    def tool(self, name, arguments=None):
        raw = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if raw.get("isError"):
            raise RuntimeError("tool failed: " + str(raw))
        data = raw.get("structuredContent")
        if data is not None:
            return data
        for value in raw.get("content", []):
            if value.get("type") == "text":
                return json.loads(value["text"])
        return raw

def run_external_acceptance_build(client, timeout):
    started = client.tool("build_start", {"profile": "ise14-implementation", "project": "ise_counter"})
    job_id = started.get("job_id")
    if not job_id:
        raise RuntimeError("build_start returned no job_id: " + str(started))
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        status = client.tool("build_status", {"job_id": job_id})
        state = status.get("state")
        if state in {"succeeded", "failed", "cancelled", "interrupted"}:
            break
        time.sleep(10)
    else:
        raise RuntimeError("build timed out, no container was stopped or removed")
    result = client.tool("build_result", {"job_id": job_id})
    if result.get("state") != "succeeded":
        raise RuntimeError("ISE build failed: " + json.dumps(result, indent=2))
    artifacts = {a.get("name"): a for a in result.get("artifacts", [])}
    bit = artifacts.get("design.bit")
    if not bit or not bit.get("sha256") or not bit.get("bytes"):
        raise RuntimeError("missing bitstream artifact checksum and size")
    hasher = hashlib.sha256()
    offset = 0
    for _ in range(4096):
        part = client.tool("build_result", {
            "job_id": job_id, "artifact": "design.bit", "offset": offset})
        fragment = base64.b64decode(part.get("chunk_base64", ""), validate=True)
        next_offset = part.get("next_offset")
        if next_offset != offset + len(fragment):
            raise RuntimeError("non-contiguous MCP artifact transfer")
        hasher.update(fragment)
        offset = next_offset
        if part.get("chunk_eof"):
            break
        if not fragment:
            raise RuntimeError("empty nonterminal MCP artifact chunk")
    else:
        raise RuntimeError("artifact exceeds bounded transfer iterations")
    if offset != bit["bytes"] or hasher.hexdigest() != bit["sha256"]:
        raise RuntimeError("bitstream length/SHA-256 mismatch through MCP")
    print("PASS: build", job_id, "bitstream bytes", offset, "sha256", hasher.hexdigest())
    print("Generic test fixture: NEVER PROGRAM this bitstream")
    return job_id

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("PANOLAB_MCP_URL", "http://127.0.0.1:8765/mcp"))
    parser.add_argument("--run-build", action="store_true", help="Start generic external ISE acceptance build test (NO FPGA PROGRAMMING)")
    parser.add_argument("--timeout", type=int, default=1500)
    args = parser.parse_args()
    token = os.environ.get("PANOLAB_MCP_TOKEN", "")
    if len(token) < 32:
        sys.exit("PANOLAB_MCP_TOKEN missing or too short (set privately; do not commit)")
    client = MCPClient(args.url, token)
    init = client.rpc("initialize", {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "panolab-ise-acceptance", "version": "1.0"}})
    print("MCP initialization:", init.get("serverInfo"))
    tools = client.rpc("tools/list")
    names = {tool["name"] for tool in tools.get("tools", [])}
    if names != TOOLS:
        sys.exit(f"FAIL: expected exactly {sorted(TOOLS)}, got {sorted(names)}")
    print("PASS: five canonical MCP tools discovered")
    info = client.tool("toolchain_info")
    print("MCP toolchain_info:", json.dumps(info, indent=2))
    if not args.run_build:
        print("PASS: MCP read-only handshake. To test vendor build, add --run-build")
        return
    if not info.get("ise_available") or not info.get("license_available"):
        sys.exit("ISE installation or license unavailable; refusing build")
    original_instance = info.get("instance_id")
    if not original_instance:
        sys.exit("No instance_id reported; persistent appliance identity cannot be checked")
    job_ids = [run_external_acceptance_build(client, args.timeout) for _ in range(2)]
    if len(set(job_ids)) != 2:
        sys.exit("FAIL: distinct builds returned identical job IDs")
    after = client.tool("toolchain_info")
    if after.get("instance_id") != original_instance:
        sys.exit("FAIL: appliance identity changed between jobs")
    for job_id in job_ids:
        if client.tool("build_status", {"job_id": job_id}).get("state") != "succeeded":
            sys.exit("FAIL: previous build status not preserved")
    print("PASS: two jobs on one persistent ISE MCP appliance; container remains running")

if __name__ == "__main__":
    try:
        main()
    except (urllib.error.URLError, ValueError, RuntimeError) as exc:
        sys.exit("FAIL: " + str(exc))
