"""Test external ISE MCP acceptance verification using fake build results.

Checks streamed bitstream reassembly, hashes, job separation, and corrupted
artifacts without Docker, licensed ISE, or any FPGA programming.
"""
import base64
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().with_name("ise_mcp_smoke_client.py")
spec=importlib.util.spec_from_file_location("panolab_ise_external_client",SCRIPT)
client=importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class FakeISE:
    def __init__(self, corrupted=False):
        self.counter=0
        self.jobs={}
        self.corrupted=corrupted
        self.bitstream=(b"EXTERNAL-TEST-BITSTREAM-NOT-FOR-PROGRAMMING\n"*5000)
    def tool(self,name,args=None):
        args=args or {}
        if name=="toolchain_info":
            return {"instance_id":"persistent-worker-01","ise_available":True,
                    "license_available":True}
        if name=="build_start":
            assert args=={"profile":"ise14-implementation","project":"ise_counter"}
            self.counter+=1
            jid=str(self.counter)
            self.jobs[jid]="succeeded"
            return {"job_id":jid,"state":"running"}
        jid=args.get("job_id")
        if jid not in self.jobs:
            raise ValueError("unknown job")
        if name=="build_status":
            return {"state":self.jobs[jid],"job_id":jid}
        if name=="build_result":
            result={"state":self.jobs[jid],"job_id":jid}
            if "artifact" in args:
                assert args["artifact"]=="design.bit"
                off=args["offset"]
                data=self.bitstream[off:off+49152]
                if self.corrupted and off==0:
                    data=b"X"+data[1:]
                result.update({"chunk_base64":base64.b64encode(data).decode("ascii"),
                               "next_offset":off+len(data),
                               "chunk_eof":off+len(data)>=len(self.bitstream)})
            else:
                result["artifacts"]=[{"name":"design.bit",
                    "bytes":len(self.bitstream),
                    "sha256":hashlib.sha256(self.bitstream).hexdigest()}]
            return result
        raise ValueError("unsupported tool")


class ExternalMCPRegression(unittest.TestCase):
    def test_two_sequential_jobs_download_and_hash(self):
        fake=FakeISE()
        with contextlib.redirect_stdout(io.StringIO()):
            first=client.run_external_acceptance_build(fake,3)
            second=client.run_external_acceptance_build(fake,3)
        self.assertNotEqual(first,second)
        self.assertEqual(fake.counter,2)
    def test_bad_artifact_is_rejected(self):
        fake=FakeISE(corrupted=True)
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError,"SHA-256 mismatch"):
                client.run_external_acceptance_build(fake,3)

if __name__=="__main__":
    unittest.main()
