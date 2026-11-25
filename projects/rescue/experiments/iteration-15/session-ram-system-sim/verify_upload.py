import struct,zlib
from pathlib import Path
# op, code, state, offset flag, offset, correlation ID, peer
expected=[(5,7,0,0,0,1,100),(1,7,0,0,0,2,100),(1,0,2,1,0,3,100),(2,0,2,1,197,4,100),(2,7,0,0,0,5,101),(2,0,2,1,197,4,100),(2,5,0,0,0,4,100),(2,5,2,1,197,6,100),(2,0,2,1,513,7,100),(3,0,3,1,513,8,100),(5,0,3,1,513,9,100),(3,0,3,1,513,8,100),(5,7,0,0,0,10,101)]
def sum16(b):
 if len(b)%2:b+=b'\0'
 n=sum(struct.unpack('!%dH'%(len(b)//2),b))
 while n>>16:n=(n&65535)+(n>>16)
 return n
frames=[bytes.fromhex(f) for f in Path('tx.hex').read_text().split('-') if f.strip()]
assert len(frames)==len(expected)
for i,(wire,(op,code,state,flag,offset,rid,peer)) in enumerate(zip(frames,expected),1):
 assert wire[:8]==b'\x55'*7+b'\xd5'
 frame=wire[8:-4];assert zlib.crc32(frame)==int.from_bytes(wire[-4:],'little')
 assert frame[:14]==bytes([2,0,0,0,0,2 if peer==100 else 3])+bytes.fromhex('0200000000010800')
 ip=frame[14:];assert ip[0]==0x45 and ip[9]==17 and sum16(ip[:20])==65535
 assert ip[12:20]==bytes([192,168,1,50,192,168,1,peer])
 udp=ip[20:int.from_bytes(ip[2:4],'big')];src,dst,n,check=struct.unpack('!HHHH',udp[:8]);assert (src,dst,n)==(49153,54321 if peer==100 else 54322,len(udp))
 assert check and sum16(ip[12:20]+struct.pack('!BBH',0,17,n)+udp)==65535
 payload=udp[8:];want=struct.pack('!BBHIBBBBI',1,op,8,rid,0,code,state,flag,offset)
 assert payload==want,(i,payload.hex(),want.hex())
 print(f'PASS request {i}: operation={op} code={code} state={state} offset={offset}; Ethernet FCS, IP/UDP checksum, correlation and endpoints')
assert 'completed all thirteen exchanges' in Path('boot-upload.log').read_text()
log=Path('boot-upload.log').read_text()
# Simulator events may interleave with individual UART characters.
import re
log=re.sub(r'\[sim\] injected request \d+\n','',log)
assert log.count('SIM: verified sealed image; journal unchanged')==1
print('PASS: actual GMII -> VexRiscv BIOS -> RAM NOR updater -> GMII, sealed image independently reverified by embedded code')
