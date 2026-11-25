import sys,struct,zlib,ipaddress
from pathlib import Path
from hashlib import sha256
sys.path.insert(0,'../manifest-core')
from fixtures import encode
raw=bytes((i*13+7)%256 for i in range(513))
m={'manifest_version':1,'image_id':'integration-fixture','image_version':'1','image_role':'application','supported_targets':[{'board_id':'pano-g2','board_revision':'b','fpga_part':'xc6slx150-2-fgg484','bsp_profile':'pano-g2-revb/1'}],'image_length':len(raw),'image_sha256':sha256(raw).digest(),'required_rescue_api':[1,0],'config_format':'xilinx-spartan6-spi','required_features':[],'build_provenance':{'git_commit':'0123456789abcdef'*2+'01234567','dependency_pins':['fixture@1'],'toolchain':'fixture'}}
manifest=encode(m)
def checksum(data):
    if len(data)%2:data+=b'\0'
    n=sum(struct.unpack('!%dH'%(len(data)//2),data))
    while n>>16:n=(n&65535)+(n>>16)
    return (~n)&65535
src=ipaddress.IPv4Address('192.168.1.100').packed;dst=ipaddress.IPv4Address('192.168.1.50').packed
first=struct.pack('!IIH',2,0,197)+raw[:197]
last=struct.pack('!IIH',2,197,len(raw)-197)+raw[197:]
seal=struct.pack('!I',2)
# op, body, correlation id, peer (100=owner,101=other)
reqs=[(5,b'',1,100),(1,struct.pack('!IIH',1,8,len(manifest)-1)+manifest[:-1],2,100),(1,struct.pack('!IIH',2,8,len(manifest))+manifest,3,100),(2,first,4,100),(2,last,5,101),(2,first,4,100),(2,first[:-1]+bytes([first[-1]^1]),4,100),(2,first,6,100),(2,last,7,100),(3,seal,8,100),(5,b'',9,100),(3,seal,8,100),(5,b'',10,101)]
lengths=[]
for i,(op,body,rid,peer) in enumerate(reqs):
    src=bytes([192,168,1,peer]);mac=bytes([2,0,0,0,0,2 if peer==100 else 3])
    payload=struct.pack('!BBHI',1,op,len(body),rid)+body
    udp=struct.pack('!HHHH',54321 if peer==100 else 54322,49153,8+len(payload),0)+payload
    ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(udp),i+1,0x4000,64,17,0,src,dst);ip=ip[:10]+struct.pack('!H',checksum(ip))+ip[12:]
    frame=(bytes.fromhex('020000000001')+mac+bytes.fromhex('0800')+ip+udp).ljust(60,b'\0');wire=b'\x55'*7+b'\xd5'+frame+struct.pack('<I',zlib.crc32(frame))
    Path(f'request{i}.hex').write_text(''.join(f'{b:02x}\n' for b in wire));lengths.append(len(wire))
Path('lengths.hex').write_text(''.join(f'{n:04x}\n' for n in lengths))
print(lengths)
