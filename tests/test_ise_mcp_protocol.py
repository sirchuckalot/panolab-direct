"""Mock-transport tests of the PanoLab MCP acceptance client.

Verifies real JSON-RPC request shapes and the five-tool sequence, without
claiming to validate the Go MCP SDK, Docker Gateway, or a licensed ISE build.
"""
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().with_name("ise_mcp_smoke_client.py")
spec = importlib.util.spec_from_file_location("ise_mcp_smoke_client", SOURCE)
clientmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clientmod)

CANONICAL = {"toolchain_info", "build_start", "build_status", "build_result", "build_cancel"}


class Response:
    def __init__(self, result):
        self.headers = {"Content-Type": "application/json"}
        self.buf = io.BytesIO(json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode())
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, maxlen):
        return self.buf.read(maxlen)


class MCPProtocolSimulation(unittest.TestCase):
    def test_five_tool_exchange(self):
        seen = []
        token = "x" * 40
        def fake_urlopen(request, timeout):
            message = json.loads(request.data)
            seen.append(message)
            self.assertEqual(request.get_header("Authorization"), "Bearer " + token)
            self.assertEqual(message["jsonrpc"], "2.0")
            name = message["method"]
            if name == "initialize":
                result = {"serverInfo": {"name": "panolab-ise14", "version": "sim"}}
            elif name == "tools/list":
                result = {"tools": [{"name": x} for x in sorted(CANONICAL)]}
            elif name == "tools/call":
                tool = message["params"]["name"]
                self.assertIn(tool, CANONICAL)
                result = {"structuredContent": {
                    "toolchain_info": {"ise_available": True, "license_available": True},
                    "build_start": {"job_id": "123", "state": "running"},
                    "build_status": {"job_id": "123", "state": "succeeded"},
                    "build_result": {"job_id": "123", "state": "succeeded",
                                     "artifacts": [{"name": "design.bit", "sha256": "a" * 64}]},
                    "build_cancel": {"job_id": "123", "state": "cancelled"},
                }[tool]}
            else:
                raise AssertionError("unexpected RPC: " + name)
            return Response(result)
        with patch.object(clientmod.urllib.request, "urlopen", side_effect=fake_urlopen):
            client = clientmod.MCPClient("http://127.0.0.1:8765/mcp", token)
            self.assertEqual(client.rpc("initialize")["serverInfo"]["name"], "panolab-ise14")
            self.assertEqual({x["name"] for x in client.rpc("tools/list")["tools"]}, CANONICAL)
            self.assertTrue(client.tool("toolchain_info")["ise_available"])
            self.assertEqual(client.tool("build_start", {"profile": "ise14-implementation", "project": "ise_counter"})["job_id"], "123")
            self.assertEqual(client.tool("build_status", {"job_id": "123"})["state"], "succeeded")
            self.assertEqual(client.tool("build_result", {"job_id": "123"})["artifacts"][0]["name"], "design.bit")
            self.assertEqual(client.tool("build_cancel", {"job_id": "123"})["state"], "cancelled")
        self.assertEqual(len(seen), 7)


if __name__ == "__main__":
    unittest.main()
