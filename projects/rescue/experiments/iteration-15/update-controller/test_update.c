#include "rescue_update.h"
#include "build/fixtures.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
enum { CAP=16*1024*1024, S=256*1024, P=256, A=2*S, B=5*S, M=7*S, J0=9*S, J1=10*S };
static const struct rescue_region map[]={
 {RESCUE_REGION_BOOT,0,S},{RESCUE_REGION_RESCUE,S,S},
 {RESCUE_REGION_APP_A,A,3*S},{RESCUE_REGION_APP_B,B,3*S},
 {RESCUE_REGION_IDENTITY,8*S,S},{RESCUE_REGION_STATE_0,J0,S},
 {RESCUE_REGION_STATE_1,J1,S},{RESCUE_REGION_RESERVED,15*S,S}};
static uint8_t nor[CAP], before[CAP];
static unsigned mutations,fail_at;
static bool allow_state, corruption;
static int rd(void *ctx,uint32_t off,uint8_t *data,size_t n) {
 (void)ctx; assert(off<=CAP && n<=CAP-off); memcpy(data,nor+off,n); return 0;
}
static bool writable(uint32_t off,size_t n) {
 return (off>=B && off<=B+3*S && n<=B+3*S-off) ||
 (allow_state && off>=J0 && off<=J1+S && n<=J1+S-off);
}
static int er(void *ctx,uint32_t off) {
 (void)ctx; assert(off%S==0 && writable(off,S));
 ++mutations;
 if(mutations==fail_at){memset(nor+off,0xff,S/2);return -1;}
 memset(nor+off,0xff,S);return 0;
}
static int pg(void *ctx,uint32_t off,const uint8_t *data,size_t n) {
 (void)ctx;assert(off%P==0 && n==P && writable(off,n));
 ++mutations;
 size_t lim=mutations==fail_at?n/2:n;
 for(size_t i=0;i<lim;i++){assert((nor[off+i]&data[i])==data[i]);nor[off+i]&=data[i];}
 if(corruption && off==B) nor[B]&=0xfe;
 return mutations==fail_at?-1:0;
}
static size_t source(void *ctx,uint64_t off,uint8_t *data,size_t n) {
 (void)ctx; if(off>sizeof raw || n>sizeof raw-off)return 0;
 memcpy(data,raw+off,n);return n;
}
static struct rescue_journal_record head;
static void fixture_image(uint32_t base,const uint8_t *image,size_t n,const uint8_t *m,size_t len,const uint8_t *hash) {
 memset(nor+base,0xff,3*S); memcpy(nor+base,image,n);
 uint8_t *p=nor+base+2*S; p[0]=0; memcpy(p+1,"PLM1",4);p[5]=(uint8_t)(len>>8);p[6]=(uint8_t)len;memcpy(p+7,hash,32);memcpy(p+39,m,len);
}
static void seed(void) {
 memset(nor,0x5a,sizeof nor);memset(nor+J0,0xff,2*S);
 memset(nor+M,0xff,S);
 head=(struct rescue_journal_record){0};
 head.sequence=8;head.state=RESCUE_RECORD_STABLE;
 head.confirmed.slot=RESCUE_JOURNAL_A;memcpy(head.confirmed.digest,old_digest,32);
 fixture_image(A,old_raw,sizeof old_raw,old_manifest,sizeof old_manifest,old_digest);
 fixture_image(B,old_raw,sizeof old_raw,old_manifest,sizeof old_manifest,old_digest);
 strcpy(head.reason,"fixture");
 assert(rescue_journal_encode(&head,nor+J0)==RESCUE_JOURNAL_OK);
 memcpy(before,nor,sizeof nor);mutations=fail_at=0;allow_state=corruption=false;
}
static int jr_test(void *ctx,unsigned sector,size_t off,uint8_t *buf,size_t n) {
 (void)ctx; if(sector>1 || off>S || n>S-off)return -1;
 return rd(NULL,(uint32_t)(sector?J1:J0)+(uint32_t)off,buf,n);
}
static struct rescue_journal_record read_head(void) {
 struct rescue_journal_io j={NULL,S,jr_test,NULL,NULL};struct rescue_journal_record current;
 assert(rescue_journal_read(&j,&current)==RESCUE_JOURNAL_OK);return current;
}
static bool return_ok(void *ctx,const void *evidence,const struct rescue_trial_launch *claim) {
 return evidence==ctx && claim->sequence==10 && claim->image.slot==RESCUE_JOURNAL_B;
}
static void preserved(void) {
 assert(memcmp(nor,before,B)==0);
 assert(memcmp(nor+B+3*S,before+B+3*S,CAP-B-3*S)==0);
}
int main(void) {
 struct rescue_flash_geometry g;
 assert(rescue_geometry_lookup(0x202018,&g));
 struct rescue_flash_io f={NULL,rd,er,pg};
 struct pl_image_policy policy={.profile=PL_TRUSTED_LAN,.detected_target={PL_PANO_G2,PL_REV_B,PL_XC6SLX150_2_FGG484,1},.rescue_api_major=1,.max_image_length=2*S};
 struct rescue_update u={&f,&g,map,sizeof map/sizeof map[0],&policy,true,true};
 struct rescue_journal_binding out={0};
 seed();
 assert(rescue_update_stage(&u,&head,RESCUE_SLOT_A,manifest,sizeof manifest,sizeof raw,source,NULL,&out)==UPDATE_PROTECTED);
 assert(mutations==0);
 u.identity_verified=false;
 assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)==UPDATE_INVALID);
 u.identity_verified=true;assert(mutations==0);
 head.sequence++;
 assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)==UPDATE_STALE);
 head.sequence--;assert(mutations==0);
 assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest-1,sizeof raw,source,NULL,&out)==UPDATE_IMAGE);
 assert(mutations==0);
 assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)==UPDATE_OK);
 assert(out.slot==RESCUE_JOURNAL_B && memcmp(out.digest,digest,32)==0);
 assert(rescue_update_verify(&u,&out));preserved();
 unsigned total=mutations;
 struct rescue_journal_binding valid=out;
 struct rescue_journal_binding old={RESCUE_JOURNAL_B,{0}}; memcpy(old.digest,old_digest,32);
 seed(); assert(rescue_update_verify(&u,&old));
 /* Repeat staging over committed old metadata with each callback interrupted. */
 memcpy(before,nor,sizeof nor);
 for(unsigned cut=1;cut<=total;cut++){
  memcpy(nor,before,sizeof nor);mutations=0;fail_at=cut;
  out=(struct rescue_journal_binding){0};
  assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)!=UPDATE_OK);
  assert(out.slot==0);preserved();
  /* Old record may remain valid only if raw bytes still match it;
   * a completed final commit followed by I/O failure may also verify. */
  if(rescue_update_verify(&u,&valid)) assert(memcmp(nor+B,raw,sizeof raw)==0);
  if(rescue_update_verify(&u,&old)) assert(memcmp(nor+B,old_raw,sizeof old_raw)==0);
  if(memcmp(nor+B,old_raw,sizeof old_raw)!=0) assert(!rescue_update_verify(&u,&old));
 }
 seed();corruption=true;
 assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)!=UPDATE_OK);
 assert(!rescue_update_verify(&u,&valid));preserved();
 seed();
 assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)==UPDATE_OK);
 allow_state=true;
 assert(rescue_update_prepare(&u,8,&out)==RESCUE_TRIAL_OK);
 struct rescue_trial_launch launch={0};
 nor[B]^=1;
 assert(rescue_update_start(&u,9,&launch)==RESCUE_TRIAL_IMAGE_REJECTED);
 assert(launch.sequence==0);
 nor[B]^=1;
 assert(rescue_update_start(&u,9,&launch)==RESCUE_TRIAL_OK);
 assert(launch.sequence==10 && launch.image.slot==RESCUE_JOURNAL_B);
 assert(rescue_update_start(&u,10,&launch)!=RESCUE_TRIAL_OK);
 int evidence=1;
 assert(rescue_update_confirm(&u,&launch,&evidence,false,return_ok,&evidence)==RESCUE_TRIAL_CONFIRM_REJECTED);
 assert(rescue_update_confirm(&u,&launch,&evidence,true,NULL,NULL)==RESCUE_TRIAL_CONFIRM_REJECTED);
 struct rescue_trial_launch wrong=launch; wrong.image.digest[0]^=1;
 assert(rescue_update_confirm(&u,&wrong,&evidence,true,return_ok,&evidence)==RESCUE_TRIAL_CONFIRM_REJECTED);
 assert(rescue_update_confirm(&u,&launch,&evidence,true,return_ok,&evidence)==RESCUE_TRIAL_OK);
 assert(rescue_update_confirm(&u,&launch,&evidence,true,return_ok,&evidence)==RESCUE_TRIAL_STALE);
 struct rescue_journal_record confirmed=read_head();
 assert(confirmed.sequence==11 && confirmed.confirmed.slot==RESCUE_JOURNAL_B && confirmed.previous.slot==RESCUE_JOURNAL_A);
 assert(rescue_update_rollback(&u,11)==RESCUE_TRIAL_OK);
 struct rescue_journal_record rolled=read_head();
 assert(rolled.sequence==12 && rolled.confirmed.slot==RESCUE_JOURNAL_A && rolled.previous.slot==RESCUE_JOURNAL_B);
 assert(rescue_update_verify(&u,&rolled.confirmed));
 unsigned prior=mutations;
 assert(rescue_update_stage(&u,&rolled,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)==UPDATE_PROTECTED);
 assert(mutations==prior);
 assert(rescue_update_verify(&u,&(struct rescue_journal_binding){RESCUE_JOURNAL_A,{0}})==false);
 seed(); assert(rescue_update_stage(&u,&head,RESCUE_SLOT_B,manifest,sizeof manifest,sizeof raw,source,NULL,&out)==UPDATE_OK);
 allow_state=true; assert(rescue_update_prepare(&u,8,&out)==RESCUE_TRIAL_OK);
 assert(rescue_update_start(&u,9,&launch)==RESCUE_TRIAL_OK);
 assert(rescue_update_failed_reset(&u,10)==RESCUE_TRIAL_OK);
 struct rescue_journal_record failed=read_head();
 assert(failed.sequence==11 && failed.confirmed.slot==RESCUE_JOURNAL_A && failed.pending.slot==RESCUE_JOURNAL_NONE && failed.state==RESCUE_RECORD_ROLLBACK_REQUIRED);
 assert(rescue_update_verify(&u,&failed.confirmed));
 assert(rescue_update_start(&u,11,&launch)!=RESCUE_TRIAL_OK);
 printf("PASS: integrated staging, protected bytes, %u interrupted callback positions, reverify, trial, mocked confirmation, rollback and failed-reset recovery\n",total);
 return 0;
}
