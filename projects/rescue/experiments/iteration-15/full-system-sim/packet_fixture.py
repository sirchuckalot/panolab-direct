import struct,zlib,ipaddress
from pathlib import Path

def checksum(data):
    if len(data)%2:data+=b'\0'
    n=sum(struct.unpack('!%dH'%(len(data)//2),data))
    while n>>16:n=(n&65535)+(n>>16)
    return (~n)&65535
src=ipaddress.IPv4Address('192.168.1.100').packed
dst=ipaddress.IPv4Address('192.168.1.50').packed
payload=b'RESCUE1 1234ABCD'
udp=struct.pack('!HHHH',54321,49152,8+len(payload),0)+payload
ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(udp),1,0x4000,64,17,0,src,dst)
ip=ip[:10]+struct.pack('!H',checksum(ip))+ip[12:]
frame=bytes.fromhex('0200000000010200000000020800')+ip+udp
frame=frame.ljust(60,b'\0');frame+=struct.pack('<I',zlib.crc32(frame))
wire=b'\x55'*7+b'\xd5'+frame
Path('request.hex').write_text(''.join(f'{b:02x}\n' for b in wire))
print(len(wire),'wire bytes')
