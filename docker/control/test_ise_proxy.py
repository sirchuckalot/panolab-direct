#!/usr/bin/env python3
"""No-Docker regression tests for the scoped ISE worker broker."""
import json
import unittest
import ise_proxy

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

if __name__=="__main__":
    unittest.main()
