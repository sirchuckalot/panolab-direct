import struct,zlib
from pathlib import Path
expected=[(5,0,1,0,0),(1,7,0,0,0),(1,0,2,1,0),(2,0,2,1,197),(2,5,2,1,197),(2,0,2,1,513),(3,0,3,1,513),(5,0,3,1,513)]
def sum16(b):
 if len(b)%2:b+=b'\0'
 n=sum(struct.unpack('!%dH'%(len(b)//2),b))
 while n>>16:n=(n&65535)+(n>>16)
 return n
frames=[bytes.fromhex(f) for f in Path('tx.hex').read_text().split('-') if f.strip()]
assert len(frames)==len(expected)
for i,(wire,(op,code,state,flag,offset)) in enumerate(zip(frames,expected),1):
 assert wire[:8]==b'\x55'*7+b'\xd5'
 frame=wire[8:-4];assert zlib.crc32(frame)==int.from_bytes(wire[-4:],'little')
 assert frame[:14]==bytes.fromhex('0200000000020200000000010800')
 ip=frame[14:];assert ip[0]==0x45 and ip[9]==17 and sum16(ip[:20])==65535
 assert ip[12:20]==bytes([192,168,1,50,192,168,1,100])
 udp=ip[20:int.from_bytes(ip[2:4],'big')];src,dst,n,check=struct.unpack('!HHHH',udp[:8]);assert (src,dst,n)==(49153,54321,len(udp))
 assert check and sum16(ip[12:20]+struct.pack('!BBH',0,17,n)+udp)==65535
 payload=udp[8:];want=struct.pack('!BBHIBBBBI',1,op,8,i,0,code,state,flag,offset)
 assert payload==want,(i,payload.hex(),want.hex())
 print(f'PASS request {i}: operation={op} code={code} state={state} offset={offset}; Ethernet FCS, IP/UDP checksum, correlation and endpoints')
assert 'completed all eight exchanges' in Path('boot-upload.log').read_text()
log=Path('boot-upload.log').read_text()
# Simulator events may interleave with individual UART characters.
import re
log=re.sub(r'\[sim\] injected request \d+\n','',log)
assert 'SIM: verified sealed image; journal unchanged' in log
print('PASS: actual GMII -> VexRiscv BIOS -> RAM NOR updater -> GMII, sealed image independently reverified by embedded code')
