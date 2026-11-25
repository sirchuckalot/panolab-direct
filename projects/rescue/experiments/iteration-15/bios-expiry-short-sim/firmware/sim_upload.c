/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Simulation-only RAM NOR. No physical mutation callbacks or flash CSRs. */
#include "sim_upload.h"
#include "managed_wire_adapter.h"
#include "managed_stream.h"
#include "rescue_protected_read.h"
#include <string.h>
#include <stdio.h>
enum { S=4096, B=5*S, B_LEN=3*S, ID=8*S, J0=9*S, J1=10*S, CAP=16*S };
static const struct rescue_region map[]={
 {RESCUE_REGION_BOOT,0,S},{RESCUE_REGION_RESCUE,S,S},
 {RESCUE_REGION_APP_A,2*S,3*S},{RESCUE_REGION_APP_B,B,B_LEN},
 {RESCUE_REGION_IDENTITY,ID,S},{RESCUE_REGION_STATE_0,J0,S},
 {RESCUE_REGION_STATE_1,J1,S},{RESCUE_REGION_RESERVED,11*S,5*S}
};
static uint8_t app[B_LEN],identity[191],journal_frame[RESCUE_JOURNAL_RECORD_BYTES];
static struct rescue_flash_geometry geom;
static bool enabled, attempted, session_ready;
static struct ns_session session;
static struct wire_session wire={.state=MW_STATE_IDLE};
static int ram_read(void *ctx,uint32_t addr,uint8_t *dst,size_t n) {
 (void)ctx;
 if(addr>=CAP || n>CAP-addr)return -1;
 for(size_t i=0;i<n;i++){
  uint32_t p=addr+(uint32_t)i;
  dst[i]=p>=B && p<B+B_LEN?app[p-B]:
    p>=ID && p<ID+sizeof identity?identity[p-ID]:
    p>=J0 && p<J0+sizeof journal_frame?journal_frame[p-J0]:0xff;
 }
 return 0;
}
static int ram_erase(void *ctx,uint32_t addr){
 (void)ctx;
 if(addr<B || addr>B+B_LEN-S || addr%S)return -1;
 memset(app+addr-B,0xff,S);return 0;
}
static int ram_program(void *ctx,uint32_t addr,const uint8_t *src,size_t n){
 (void)ctx;
 if(addr<B || addr>B+B_LEN-256 || addr%256 || n!=256)return -1;
 for(size_t i=0;i<n;i++)if((app[addr-B+i]&src[i])!=src[i])return -1;
 for(size_t i=0;i<n;i++)app[addr-B+i]&=src[i];
 return 0;
}
static const struct rescue_flash_io io={NULL,ram_read,ram_erase,ram_program};
static const struct pl_image_policy policy={
 .profile=PL_TRUSTED_LAN,.detected_target={PL_PANO_G2,PL_REV_B,PL_XC6SLX150_2_FGG484,1},
 .rescue_api_major=1,.max_image_length=2*S
};
static struct rescue_update update={&io,&geom,map,sizeof map/sizeof map[0],&policy,false,true};
bool sim_upload_init(const struct rescue_flash_geometry *g){
 if(attempted){enabled=false;return false;}
 attempted=true;
 if(!g || g->jedec_id!=0x7f1234 || g->capacity!=CAP || g->erase_size!=S || g->page_size!=256)return false;
 geom=*g;
 memset(app,0xff,sizeof app);
 struct rescue_identity x={.version=1,.device_id={17},.board_id="pano-g2",.board_revision="b",.fpga_part="xc6slx150-2-fgg484",.mac={{2,0,0,0,0,23}},.serial="sim-only",.source_provenance="RAM fixture, not factory"};
 x.integrity_crc=rescue_identity_crc(&x);
 memcpy(identity,"PLID",4);size_t p=4;identity[p++]=x.version;
 #define PUT(f) do {memcpy(identity+p,&x.f,sizeof x.f);p+=sizeof x.f;}while(0)
 PUT(device_id);PUT(board_id);PUT(board_revision);PUT(fpga_part);PUT(mac.bytes);PUT(serial);PUT(source_provenance);
 #undef PUT
 for(unsigned i=0;i<4;i++)identity[p++]=(uint8_t)(x.integrity_crc>>(24-8*i));
 if(p!=sizeof identity)return false;
 struct rescue_journal_record j={.sequence=8,.confirmed={RESCUE_JOURNAL_A,{1}},.state=RESCUE_RECORD_STABLE,.reason="fixture"};
 if(rescue_journal_encode(&j,journal_frame)!=RESCUE_JOURNAL_OK)return false;
 struct rescue_persistent_state state;
 if(rescue_protected_inspect(&geom,map,sizeof map/sizeof map[0],ram_read,NULL,NULL,0,&state)!=RESCUE_INSPECTION_OK ||
 state.identity_status!=RESCUE_PERSISTENT_VALID || state.journal_status!=RESCUE_PERSISTENT_VALID)return false;
 update.identity_verified=true;
 enabled=pl_managed_init(&update,RESCUE_SLOT_B,0)==PL_UPLOAD_OK;
 return enabled;
}
static bool same_frame(const uint8_t *a,const uint8_t *b,size_t n){for(size_t i=0;i<n;i++)if(a[i]!=b[i])return false;return true;}
static enum mw_code checked_seal(void *ctx,uint32_t id,struct mw_progress *p){
 enum mw_code r=managed_wire_callbacks.seal(ctx,id,p);
 if(r==MW_OK){
  struct rescue_journal_binding binding;
  struct rescue_journal_record head;
  uint8_t frame[RESCUE_JOURNAL_RECORD_BYTES];
  if(pl_managed_binding(wire.id,&binding) && pl_managed_verify(&binding) && pl_managed_journal_read(&head)==RESCUE_JOURNAL_OK && rescue_journal_encode(&head,frame)==RESCUE_JOURNAL_OK && same_frame(frame,journal_frame,sizeof frame)) puts("SIM: verified sealed image; journal unchanged");
  else {wire.locked=1;return MW_INTERNAL;}
 }
 return r;
}
bool sim_upload_session_init(ns_clock_fn clock,ns_reply_fn reply){
 if(!enabled || session_ready)return false;
 struct mw_callbacks cb=managed_wire_callbacks; cb.seal=checked_seal;
 session_ready=ns_init(&session,&cb,clock,reply,&wire,20)!=0;
 return session_ready;
}
void sim_upload_receive(const struct ns_peer *peer,const uint8_t *data,size_t length){
 if(enabled && session_ready) (void)ns_receive(&session,peer,data,length);
}
void sim_upload_tick(void){if(enabled && session_ready)ns_tick(&session);}
