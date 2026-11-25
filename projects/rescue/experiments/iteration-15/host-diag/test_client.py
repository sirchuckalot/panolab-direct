import ctypes
import unittest
from pathlib import Path
import rescue_diag_client as client

lib=ctypes.CDLL(str(Path(__file__).resolve().parent/"build"/"diag.so"))
handle=lib.rescue_diag_handle
handle.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t]
handle.restype=ctypes.c_size_t
def firmware_reply(request,probe=0):
    buf=ctypes.create_string_buffer(160)
    n=handle(request,len(request),probe,buf,len(buf))
    return buf.raw[:n]
class Tests(unittest.TestCase):
    def test_real_c_handler(self):
        for state in (0,1):
            r=client.parse_reply(firmware_reply(client.request_bytes("1234ABCD"),state),"1234ABCD")
            self.assertEqual(r["flash_probe"],"ok" if state==0 else "failed")
    def test_wrong_id_and_truncations(self):
        data=firmware_reply(client.request_bytes("1234ABCD"))
        for i in range(len(data)):
            with self.assertRaises(ValueError):client.parse_reply(data[:i],"1234ABCD")
        for d in (data+b"mode=recovery-only\n",data+b"extra=1\n",data.replace(b"paired=false",b"paired=true")):
            with self.assertRaises(ValueError):client.parse_reply(d,"1234ABCD")
        with self.assertRaises(ValueError):client.parse_reply(data,"ABCD1234")
    def test_mock_transport(self):
        class Fake:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def settimeout(self,n):self.timeout=n
            def connect(self,d):assert d==("192.168.1.50",49152)
            def sendall(self,data):self.data=data
            def recv(self,n):return firmware_reply(self.data)
        self.assertEqual(client.query("192.168.1.50",socket_factory=lambda *a:Fake())["warning"],"LAB ONLY")
        for addr in ("8.8.8.8","224.0.0.1","0.0.0.0","192.168.1.255"):
            with self.assertRaises(ValueError):client.query(addr,socket_factory=lambda *a:self.fail("unexpected socket"))
if __name__=="__main__":unittest.main()
