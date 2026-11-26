#!/usr/bin/env python3
"""No-Docker regression tests for the scoped ISE worker broker."""
import ast
import base64
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import types
from unittest import mock
import unittest
import ise_proxy

JOB = "1795652101955866441"

REPORT_HEAD = b"""Release 14.7 Trace  (lin64)
Copyright (c) Xilinx.
Timing constraint: TS_clk = PERIOD TIMEGRP "private_clk" 10 ns HIGH 50%;
  186 paths analyzed, 92 endpoints analyzed, 3 failing endpoints
  4 timing errors detected. (3 setup errors, 1 hold error, 0 component switching limit errors)
  Minimum period is 10.375ns.
Slack (setup path): -0.375ns (requirement - (data path - clock skew + uncertainty))
Slack (setup path): 0.100ns (requirement - (data path - clock skew + uncertainty))
Slack (hold path): -25ps (requirement - data path)
  Source: /private/customer/SUPER_SECRET
Timing constraint: TS_io = OFFSET IN 8 ns BEFORE "private_clk";
  2 paths analyzed, 1 endpoint analyzed, 0 failing endpoints
  0 timing errors detected. (0 setup errors, 0 hold errors, 0 component switching limit errors)
"""
REPORT_TAIL = b"""Summary:
  4 timing errors detected. (3 setup errors, 1 hold error, 0 component switching limit errors)
Timing summary:
---------------
Timing errors: 4  Score: 400 (Setup/Max: 375, Hold: 25)
Constraints cover 188 paths, 120 nets, and 220 connections
Not all constraints were met.
Design statistics:
  Minimum period: 10.375ns{1} (Maximum frequency: 96.386MHz)
"""
REPORT = REPORT_HEAD + b" " * (71041 - len(REPORT_HEAD) - len(REPORT_TAIL)) + b"\n" + REPORT_TAIL

class ISEProxyContracts(unittest.TestCase):
    def command(self,argv,timeout):
        if argv[:3] == ["docker","inspect","--format"]:
            template=argv[3]
            if ".HostConfig.CapDrop" in template:
                return {"ok":True,"stdout":json.dumps(["ALL"])+"|"+json.dumps(["no-new-privileges:true"])}
            if ".Mounts" in template:
                mounts=[
                    {"Destination":dest,"Type":"bind","RW":write}
                    for dest,write in (("/opt/Xilinx",False),("/licenses/Xilinx.lic",False),
                                       ("/projects",False),("/results",True),
                                       ("/run/secrets/ise-worker-token",False))
                ]
                return {"ok":True,"stdout":json.dumps(mounts)}
            return {"ok":True,"stdout":"/panolab-direct-ise14-worker-1|true|true|none|false|true|0:0"}
        if argv[:3] == ["docker","exec","--user"]:
            if "project_manifest_readable" in argv[-1] and "WORKER_PROBE" not in argv[-1]:
                return {"ok":True,"stdout":json.dumps({
                    "project_directory":True,"project_manifest_readable":True,
                    "project_verilog_readable":True,"project_constraints_readable":True,
                    "results_directory":True,"results_writable":True,
                    "ise_settings_readable":True,"license_file_readable":True
                })}
            if argv[-2] == "toolchain_info":
                return {"ok":True,"stdout":json.dumps({"ok":True,"data":{
                    "ise_available":True,"license_available":True,"vendor":"Xilinx"}})}
            return {"ok":True,"stdout":json.dumps({"ok":False,"category":"MISSING_FILE"})}
        raise AssertionError("unexpected invocation")

    def test_toolchain(self):
        result=ise_proxy.call_worker({"tool":"toolchain_info"},self.command)
        self.assertTrue(result["ok"])
        self.assertTrue(result["ise_available"])

    def test_read_only_worker_diagnostics(self):
        result=ise_proxy.call_worker({"tool":"diagnose"},self.command)
        self.assertTrue(result["ok"],result)
        self.assertTrue(result["results_writable"],result)
        self.assertTrue(result["project_manifest_readable"],result)

    def test_build_rejection_carries_only_category(self):
        result=ise_proxy.call_worker({"tool":"build_start","arguments":{
            "Profile":"ise14-implementation","Project":"panolab_ise_smoke"}},self.command)
        self.assertEqual(result,{"ok":False,"error":"MISSING_FILE"})

    def test_reject_unscoped_docker_operation_and_bad_identifiers(self):
        for request in (
            {"tool":"shell"},
            {"tool":"build_start","arguments":{"Profile":"ise14-implementation","Project":"../../private"}},
            {"tool":"build_result","arguments":{"ID":"../../etc"}},
            {"tool":"build_result","arguments":{"ID":"1234567890123456789","Artifact":"Xilinx.lic"}},
        ):
            with self.subTest(request=request):
                self.assertFalse(ise_proxy.call_worker(request,self.command)["ok"])

    def test_isolated_license_network_is_allowed(self):
        def isolated(argv,timeout):
            if argv[:3]==["docker","network","inspect"]:
                return {"ok":True,"stdout":"true|true"}
            if argv[:3]==["docker","inspect","--format"]:
                if ".NetworkSettings.Networks" in argv[3]:
                    return {"ok":True,"stdout":json.dumps({
                        ise_proxy.LICENSE_NETWORK:{"MacAddress":"02:42:11:22:33:44"}})}
                result=self.command(argv,timeout)
                if ".HostConfig.NetworkMode" in argv[3]:
                    result["stdout"]=result["stdout"].replace(
                        "|none|","|"+ise_proxy.LICENSE_NETWORK+"|")
                return result
            return self.command(argv,timeout)
        answer=ise_proxy.call_worker({"tool":"toolchain_info"},isolated)
        self.assertTrue(answer["ok"],answer)

    def test_external_license_network_rejected(self):
        def not_internal(argv,timeout):
            if argv[:3]==["docker","network","inspect"]:
                return {"ok":True,"stdout":"false|true"}
            if argv[:3]==["docker","inspect","--format"] and ".HostConfig.NetworkMode" in argv[3]:
                result=self.command(argv,timeout)
                result["stdout"]=result["stdout"].replace(
                    "|none|","|"+ise_proxy.LICENSE_NETWORK+"|")
                return result
            return self.command(argv,timeout)
        answer=ise_proxy.call_worker({"tool":"toolchain_info"},not_internal)
        self.assertEqual(answer["error"],"ISE_LICENSE_NETWORK_NOT_INTERNAL")

    def test_networked_worker_is_rejected(self):
        def bad(argv,timeout):
            result=self.command(argv,timeout)
            if argv[:3]==["docker","inspect","--format"] and ".Name" in argv[3]:
                result["stdout"]=result["stdout"].replace("|none|","|bridge|")
            return result
        self.assertEqual(ise_proxy.call_worker({"tool":"toolchain_info"},bad)["error"],
                         "ISE_WORKER_SECURITY_CONTRACT_FAILED")

    def test_raw_vendor_logs_are_never_returned(self):
        result=ise_proxy.filtered_result("build_result",{
            "job_id":"1234567890123456789","state":"failed","exit_code":1,
            "log_tail":"ERROR: could not read /private/customer/license token=SECRET-123",
            "artifacts":[{"name":"xst.log","bytes":100,"sha256":"a"*64}]})
        self.assertTrue(result["ok"])
        self.assertNotIn("log_tail",result)
        self.assertNotIn("SECRET-123",json.dumps(result))
        self.assertIn("ERROR",result["log_categories"])

class TimingResultContracts(unittest.TestCase):
    def setUp(self):
        self.report = REPORT
        self.artifact = {"name": "design.twr", "bytes": len(self.report),
                         "sha256": hashlib.sha256(self.report).hexdigest()}
        self.identity = {"job_id": JOB, "state": "succeeded", "exit_code": 0,
                         "project": "fixture", "profile": "ise14-implementation"}
        self.metadata = dict(self.identity, artifacts=[self.artifact],
                             log_tail="ERROR: license /private/SUPER_SECRET " + "\x01" * 24576)
        self.requests = []
        self.page = lambda page: page
        self.corrupt_stdout = lambda stdout: stdout

    def command(self, argv, timeout):
        if argv[1] != "exec":
            return ISEProxyContracts.command(self, argv, timeout)
        self.assertEqual(argv[:7], ["docker", "exec", "--user", "0:0",
                                   ise_proxy.WORKER, "python", "-c"])
        self.assertEqual(argv[-2], "build_result")
        args = json.loads(argv[-1])
        self.requests.append(args)
        offset = args.get("offset")
        if offset is None:
            data = self.metadata
        else:
            self.assertEqual(args, {"artifact": "design.twr", "job_id": JOB, "offset": offset})
            fragment = self.report[offset:offset + ise_proxy.CHUNK_BYTES]
            end = offset + len(fragment)
            data = dict(self.identity, artifacts=[], next_offset=end,
                        chunk_base64=base64.b64encode(fragment).decode())
            if offset:
                data["chunk_offset"] = offset
            if end == len(self.report):
                data["chunk_eof"] = True
            data = self.page(data)
        text = json.dumps(data)
        result = {"content": [{"type": "text", "text": text}]}
        if not offset:
            result["structuredContent"] = data
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()
        def urlopen(request, timeout):
            _, fields = request
            message = json.loads(fields["data"])
            self.assertEqual(message["params"], {"name": "build_result", "arguments": args})
            return io.BytesIO(body)
        urllib2 = types.SimpleNamespace(Request=lambda *a, **kw: (a, kw),
                                       urlopen=urlopen, HTTPError=type("HTTPError", (Exception,), {}))
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"urllib2": urllib2}), mock.patch.object(
                sys, "argv", ["-c", *argv[-2:]]), redirect_stdout(out):
            exec(argv[-3], {"basestring": str, "open": lambda *_: io.BytesIO(b"test bearer")})
        stdout = self.corrupt_stdout(out.getvalue())
        return {"ok": True, "stdout": stdout[-24000:]}

    def result(self, artifact="design.twr"):
        return ise_proxy.call_worker({"tool": "build_result",
                                     "arguments": {"ID": JOB, "Artifact": artifact}}, self.command)

    def test_metadata_only(self):
        response = self.result("")
        self.assertEqual(response, {"ok": True, "tool": "build_result", "job_id": JOB,
                                   "state": "succeeded", "exit_code": 0, "artifacts": [self.artifact],
                                   "logs_truncated": False, "log_categories": ["ERROR", "LICENSE_MENTION"]})
        self.assertEqual(self.requests, [{"job_id": JOB}])

    def test_both_broker_routes_verify_complete_report(self):
        source = Path(__file__).with_name("broker.py")
        if not source.is_file():
            source = Path("/usr/local/bin/panolab-broker.py")
        function = next(node for node in ast.parse(source.read_text()).body
                        if isinstance(node, ast.FunctionDef) and node.name == "dispatch")
        env = {"TRUSTED_MAINTENANCE": False, "ise_proxy": ise_proxy, "command": self.command}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), env)
        for request in ({"action": "ise_rpc", "tool": "build_result",
                         "arguments": {"ID": JOB, "Artifact": "design.twr"}},
                        {"action": "exec", "argv": ["@ise14", "build_result", JOB, "design.twr"]}):
            with self.subTest(route=request["action"]):
                self.requests.clear()
                response = env["dispatch"](request)
                self.assertTrue(response["ok"], response)
                self.assertEqual([r.get("offset") for r in self.requests],
                                 [None, *range(0, 71042, 8192)])
                timing = response["timing"]
                self.assertEqual(timing["artifact"], self.artifact)
                self.assertEqual(timing["constraint_status"], "constrained")
                self.assertEqual(timing["overall"]["setup_errors"], 3)
                self.assertEqual(timing["overall"]["hold_errors"], 1)
                self.assertEqual(timing["overall"]["covered_paths"], 188)
                self.assertFalse(timing["overall"]["all_constraints_met"])
                clock, offset = timing["constraints"]
                self.assertEqual(clock["requested_period_ns"], "10")
                self.assertEqual(clock["worst_reported_setup_slack_ns"], "-0.375")
                self.assertEqual(clock["worst_reported_hold_slack_ns"], "-0.025")
                self.assertEqual(offset["requested_offset_ns"], "8")
                serialized = json.dumps(response)
                for secret in ("SUPER_SECRET", "/private", "private_clk", "chunk_base64", "log_tail"):
                    self.assertNotIn(secret, serialized)
                self.assertLess(len(serialized), 65536)

    def test_reject_bad_metadata_and_nonterminal_job(self):
        for changes, category in (
            ({"artifacts": []}, "ISE_TIMING_ARTIFACT_MISSING"),
            ({"artifacts": [dict(self.artifact, bytes=ise_proxy.MAX_REPORT+1)]},
             "ISE_TIMING_ARTIFACT_SIZE_INVALID"),
            ({"artifacts": [dict(self.artifact, sha256="abc")]}, "ISE_RESULT_INVALID"),
            ({"artifacts": [self.artifact, self.artifact]}, "ISE_RESULT_INVALID"),
            ({"job_id": "12345678901234"}, "ISE_RESULT_JOB_MISMATCH"),
            ({"state": "running", "exit_code": -1}, "ISE_TIMING_JOB_NOT_COMPLETE"),
        ):
            with self.subTest(changes=changes), mock.patch.dict(self.metadata, changes):
                self.assertEqual(self.result(), {"ok": False, "error": category})
        self.assertTrue(all("artifact" not in req for req in self.requests))
        self.assertEqual(self.result("design.bit")["error"], "INVALID_RESULT_ARGUMENTS")

    def test_bad_pages_and_corrupt_digest(self):
        cases = (
            (lambda p: dict(p, chunk_offset=0) if p.get("chunk_offset") else p, "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, chunk_offset=True), "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, next_offset=2), "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, chunk_eof=True), "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, chunk_eof=False), "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, chunk_base64="!" * 10924), "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, chunk_base64=p["chunk_base64"][:-4]), "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, project="other"), "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: {}, "ISE_TIMING_CHUNK_INVALID"),
            (lambda p: dict(p, chunk_base64="A"+p["chunk_base64"][1:]),
             "ISE_TIMING_ARTIFACT_INTEGRITY_FAILED"),
        )
        for page, error in cases:
            with self.subTest(error=error, page=page):
                self.page = page
                self.assertEqual(self.result(), {"ok": False, "error": error})

    def test_reject_truncated_oversized_or_duplicate_rpc_frames(self):
        for transform, error in (
            (lambda wire: wire[:-5], "ISE_RPC_UNREADABLE"),
            (lambda wire: "x"*24000 + wire, "ISE_RPC_RESPONSE_TOO_LARGE"),
            (lambda wire: '{"ok":true,' + wire[1:], "ISE_RPC_UNREADABLE"),
        ):
            with self.subTest(error=error):
                self.corrupt_stdout = transform
                self.assertEqual(self.result(), {"ok":False, "error":error})

    def test_unknown_unconstrained_and_incomplete_timing_never_pass(self):
        head = b"Release 14.7 Trace (lin64)\nTiming summary:\n"
        score = b"Timing errors: 0 Score: 0 (Setup/Max: 0, Hold: 0)\n"
        for report, status in (
            (head + score + b"All constraints were met.\n", "unknown"),
            (head + score + b"Constraints cover 0 paths, 0 nets, and 0 connections\n", "unconstrained"),
            (REPORT.split(b"Not all constraints")[0], "incomplete"),
        ):
            with self.subTest(status=status):
                evidence = ise_proxy.parse_timing_report(report)
                self.assertEqual(evidence["constraint_status"], status)
                self.assertNotIn("all_constraints_met", evidence["overall"])
        for report in (REPORT_HEAD, REPORT[:-1], REPORT.replace(b"Timing errors: 4", b"Timing errors: 0")):
            with self.subTest(length=len(report)), self.assertRaises(ValueError):
                ise_proxy.parse_timing_report(report)

    def test_exact_page_boundary_and_clean_constrained_result(self):
        body = (
            b"Release 14.7 Trace (lin64)\n"
            b'Timing constraint: TS_clk = PERIOD TIMEGRP "test_clk" 8 ns HIGH 50%;\n'
            b"10 paths analyzed, 5 endpoints analyzed, 0 failing endpoints\n"
            b"0 timing errors detected. (0 setup errors, 0 hold errors)\n"
            b"Slack (setup path): 0.250ns\n"
            b"Slack (hold path): 0.125ns\n"
            b"Timing summary:\n"
            b"Timing errors: 0 Score: 0 (Setup/Max: 0, Hold: 0)\n"
            b"Constraints cover 10 paths, 5 nets, and 6 connections\n"
            b"All constraints were met.\n"
        )
        self.report = body + b" " * (ise_proxy.CHUNK_BYTES - len(body) - 1) + b"\n"
        self.artifact.update(bytes=len(self.report), sha256=hashlib.sha256(self.report).hexdigest())
        result = self.result()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["timing"]["overall"]["all_constraints_met"])
        self.assertEqual(len(self.requests), 2)
        with self.assertRaises(ValueError):
            ise_proxy.parse_timing_report(body.replace(b"0.125ns", b"-0.125ns"))

    def test_license_proof_is_bounded_and_coherent(self):
        data = {"vendor": "Xilinx", "toolchain_version": "ISE 14.7",
                "ise_available": True, "license_available": True, "license_validated": True,
                "license_validation_status": "validated", "license_validation_job_id": JOB,
                "private_identity": "SUPER_SECRET"}
        result = ise_proxy.filtered_result("toolchain_info", data)
        self.assertTrue(result["license_validated"])
        self.assertEqual(result["license_validation_job_id"], JOB)
        self.assertNotIn("SUPER_SECRET", json.dumps(result))
        for changes, status in (({"license_available": False}, "unavailable"),
                                ({"license_validation_job_id": "/private"}, "not_yet_validated")):
            result = ise_proxy.filtered_result("toolchain_info", dict(data, **changes))
            self.assertFalse(result["license_validated"])
            self.assertEqual(result["license_validation_status"], status)
            self.assertNotIn("license_validation_job_id", result)


if __name__=="__main__":
    unittest.main()
