import ctypes
import contextlib
import io
import runpy
import os
import unittest
from pathlib import Path
from host_management import HostManagementClient, Progress, State, UncertainOutcome

class TestFirmwareBridge(unittest.TestCase):
    def test_real_firmware_transport(self):
        here=Path(__file__).resolve().parent
        # Existing independent deterministic fixture generator, no network.
        old=os.getcwd()
        import sys
        sys.path.insert(0,str(here.parent/'manifest-core'))
        try:
            os.chdir(here.parent/'session-ram-system-sim')
            # Extract fixture definitions without generating packet files.
            src=Path('packet_fixture.py').read_text().split('lengths=[]')[0]
            ns={}
            exec(compile(src,'fixture-prefix','exec'),ns)
        finally:
            os.chdir(old);sys.path.pop(0)
        raw,manifest=ns['raw'],ns['manifest']
        lib=ctypes.CDLL(str(here/'build/bridge.so'))
        lib.bridge_init.restype=ctypes.c_int
        lib.bridge_exchange.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
        lib.bridge_exchange.restype=ctypes.c_int
        lib.bridge_advance.argtypes=[ctypes.c_uint64]
        self.assertEqual(lib.bridge_init(),1)
        seen=[]
        def transport(request):
            out=ctypes.create_string_buffer(16)
            self.assertEqual(lib.bridge_exchange(request,len(request),out),16)
            # Drop the first response to every unique request after actual C dispatch.
            if request not in seen:
                seen.append(request)
                raise TimeoutError('simulated lost reply')
            return out.raw
        client=HostManagementClient(transport)
        self.assertEqual(client.begin(1,8,manifest),Progress(State.OPEN,0))
        self.assertEqual(client.chunk(raw[:197]),Progress(State.OPEN,197))
        self.assertEqual(client.stream(io.BytesIO(raw[197:])),Progress(State.OPEN,513))
        self.assertEqual(client.seal(),Progress(State.SEALED,513))
        self.assertEqual(client.status(),Progress(State.SEALED,513))
        self.assertEqual(len(seen),5)
        self.assertEqual(client.begin(2,8,manifest),Progress(State.OPEN,0))
        lib.bridge_advance(1000)
        with self.assertRaises(UncertainOutcome):client.chunk(raw[:197])
        with self.assertRaises(UncertainOutcome):client.status()
        self.assertEqual(len(seen),7)
        print('PASS: real C session + RAM updater, lost replies, exactly acknowledged offsets, lease cancellation and host lockout')
if __name__=='__main__':unittest.main()
