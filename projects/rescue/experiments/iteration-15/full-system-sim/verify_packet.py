import sys,struct,zlib,ipaddress
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'host-diag'))
from rescue_diag_client import parse_reply
wire=bytes.fromhex(Path('tx.hex').read_text())
assert wire[:8]==b'\x55'*7+b'\xd5'
frame=wire[8:-4]
assert zlib.crc32(frame)==int.from_bytes(wire[-4:],'little'), 'Ethernet FCS mismatch'
assert frame[:14]==bytes.fromhex('0200000000020200000000010800')
ip=frame[14:]; assert ip[0]==0x45 and ip[9]==17
length=int.from_bytes(ip[2:4],'big');assert len(ip)>=length
assert str(ipaddress.IPv4Address(ip[12:16]))=='192.168.1.50'
assert str(ipaddress.IPv4Address(ip[16:20]))=='192.168.1.100'
def csum(data):
    if len(data)%2:data+=b'\0'
    n=sum(struct.unpack('!%dH'%(len(data)//2),data))
    while n>>16:n=(n&65535)+(n>>16)
    return n
assert csum(ip[:20])==65535,'IP checksum'
udp=ip[20:length];src,dst,ulen,check=struct.unpack('!HHHH',udp[:8]);assert (src,dst)==(49152,54321) and ulen==len(udp)
assert check and csum(ip[12:20]+struct.pack('!BBH',0,17,ulen)+udp)==65535,'UDP checksum'
status=parse_reply(udp[8:],'1234ABCD'); assert status['flash_probe']=='ok'
print('PASS: GMII receive -> real BIOS -> GMII transmit; MAC/IP/UDP endpoints, FCS, IPv4/UDP checksum, request ID and response fields')
print(udp[8:].decode('ascii'),end='')
