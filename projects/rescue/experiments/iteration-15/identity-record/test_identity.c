#include "identity_record.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static const char magic[]="PLID";
int main(void) {
 struct rescue_identity src={0},out={0};
 src.version=1;src.device_id[0]=17;strcpy(src.board_id,"pano-g2");
 strcpy(src.board_revision,"b");strcpy(src.fpga_part,"xc6slx150-2-fgg484");
 src.mac.bytes[0]=2;src.mac.bytes[5]=23;strcpy(src.serial,"synthetic");
 strcpy(src.source_provenance,"fixture-not-factory");src.integrity_crc=rescue_identity_crc(&src);
 uint8_t record[PANOLAB_IDENTITY_RECORD_BYTES];size_t pos=4;memcpy(record,magic,4);record[pos++]=src.version;
#define PUT(field) do{memcpy(record+pos,&src.field,sizeof src.field);pos+=sizeof src.field;}while(0)
 PUT(device_id);PUT(board_id);PUT(board_revision);PUT(fpga_part);PUT(mac.bytes);PUT(serial);PUT(source_provenance);
#undef PUT
 for(unsigned i=0;i<4;i++)record[pos++]=(uint8_t)(src.integrity_crc>>(24-8*i));
 assert(pos==sizeof record);
 assert(rescue_identity_decode(record,sizeof record,NULL,0,&out));
 assert(out.integrity_crc==src.integrity_crc && memcmp(out.mac.bytes,src.mac.bytes,6)==0);
 struct rescue_identity saved=out;
 for(size_t i=0;i<sizeof record;i++){
  for(unsigned bit=0;bit<8;bit++){
   record[i]^=(uint8_t)(1u<<bit);
   assert(!rescue_identity_decode(record,sizeof record,NULL,0,&out));
   assert(memcmp(&out,&saved,sizeof out)==0);
   record[i]^=(uint8_t)(1u<<bit);
  }
  assert(!rescue_identity_decode(record,i,NULL,0,&out));
 }
 assert(!rescue_identity_decode(record,sizeof record,&src.mac,1,&out));
 assert(!rescue_identity_decode(record,sizeof record,NULL,1,&out));
 printf("PASS: normalized identity decode, %zu single-bit corruptions, all truncated prefixes, duplicate MAC rejection\n",sizeof record*8);
 return 0;
}
