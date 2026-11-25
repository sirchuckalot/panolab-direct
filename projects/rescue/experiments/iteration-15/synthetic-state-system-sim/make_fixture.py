from pathlib import Path
import zlib
p=lambda s,n:s.encode().ljust(n,b'\0')
body=bytes([1,17])+bytes(15)+p('pano-g2',24)+p('b',8)+p('xc6slx150-2-fgg484',32)+bytes([2,0,0,0,0,23])+p('simulation',32)+p('synthetic fixture',64)
i=b'PLID'+body+zlib.crc32(body).to_bytes(4,'big');assert len(i)==191
j=b'RSJ1'+bytes([1])+(8).to_bytes(8,'big')+bytes([1,0xab])+bytes(31)+bytes(66)+bytes(2)+p('confirmed',32);assert len(j)==146
j+=zlib.crc32(j).to_bytes(4,'big')+b'\0';assert len(j)==151
# Valid frame with corrupt padding: reader must reject journal. Second sector invalid.
Path('identity.hex').write_text(''.join(f'{x:02x}\n' for x in i));Path('journal.hex').write_text(''.join(f'{x:02x}\n' for x in j))
