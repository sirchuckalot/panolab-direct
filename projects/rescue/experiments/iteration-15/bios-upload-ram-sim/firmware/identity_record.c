/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "identity_record.h"
static void copy(void *dst,const uint8_t *src,size_t len) {
 unsigned char *d=dst;for(size_t i=0;i<len;i++)d[i]=src[i];
}
bool rescue_identity_decode(const uint8_t *data,size_t n,const struct rescue_mac *inventory,size_t count,struct rescue_identity *out) {
 if(!data || !out || n!=PANOLAB_IDENTITY_RECORD_BYTES ||
    data[0]!='P'||data[1]!='L'||data[2]!='I'||data[3]!='D')return false;
 struct rescue_identity tmp={0};size_t offset=4;
 tmp.version=data[offset++];
#define GET(field) do {copy(&tmp.field,data+offset,sizeof tmp.field);offset+=sizeof tmp.field;}while(0)
 GET(device_id);GET(board_id);GET(board_revision);GET(fpga_part);GET(mac.bytes);GET(serial);GET(source_provenance);
#undef GET
 tmp.integrity_crc=0;
 for(size_t i=0;i<4;i++)tmp.integrity_crc=(tmp.integrity_crc<<8)|data[offset++];
 if(offset!=n || !rescue_identity_valid(&tmp,inventory,count))return false;
 *out=tmp;return true;
}
