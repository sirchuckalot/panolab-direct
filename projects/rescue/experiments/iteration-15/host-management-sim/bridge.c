/* Simulation-only bridge, no sockets or hardware interfaces. */
#include "../bios-session-ram-sim/firmware/sim_upload.h"
#include <string.h>
static uint64_t now_ms;
static unsigned replies;
static uint8_t response[16];
static const struct ns_peer peer={{192,168,1,100},54321,{2,0,0,0,0,2}};
static uint64_t clock_ms(void *ctx){(void)ctx;return now_ms;}
static void receive_reply(void *ctx,const struct ns_peer *p,const uint8_t *b,size_t n){
 (void)ctx;
 if(n==sizeof response && p->port==peer.port){memcpy(response,b,n);++replies;}
}
int bridge_init(void){
 struct rescue_flash_geometry g={0x7f1234,65536,4096,256};
 return sim_upload_init(&g)&&sim_upload_session_init(clock_ms,receive_reply);
}
int bridge_exchange(const uint8_t *data,size_t n,uint8_t *out){
 unsigned before=replies;
 sim_upload_receive(&peer,data,n);sim_upload_tick();
 if(replies!=before+1)return 0;
 memcpy(out,response,16);return 16;
}
void bridge_advance(uint64_t delta){now_ms+=delta;sim_upload_tick();}
