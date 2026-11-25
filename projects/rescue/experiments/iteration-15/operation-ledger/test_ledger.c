/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "op_ledger.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
typedef struct {uint8_t bytes[OL_FRAME_SIZE];} medium;
static medium a,b;
static unsigned event,cut,prefix;
static bool read_failure;
static bool stop(void){return ++event==cut;}
static ol_read_result rd(void *ctx,uint8_t *out){
 medium *m=ctx;
 if(read_failure)return OL_READ_ERROR;
 bool empty=true;for(unsigned i=0;i<OL_FRAME_SIZE;i++)if(m->bytes[i]!=255)empty=false;
 memcpy(out,m->bytes,OL_FRAME_SIZE);
 return empty?OL_READ_EMPTY:OL_READ_FRAME;
}
static bool erase(void *ctx){
 medium *m=ctx;bool fail=stop();
 memset(m->bytes,255,fail?prefix:OL_FRAME_SIZE);return !fail;
}
static bool body(void *ctx,const uint8_t *data){
 medium *m=ctx;bool fail=stop();unsigned n=fail?prefix:OL_BODY_SIZE;
 for(unsigned i=0;i<n;i++){assert((m->bytes[i]&data[i])==data[i]);m->bytes[i]&=data[i];}
 return !fail;
}
static bool mark(void *ctx,uint8_t v){
 medium *m=ctx;bool fail=stop();
 if(!fail || prefix==1)m->bytes[OL_BODY_SIZE]&=v;
 return !fail;
}
static ol_store store(medium *m){return (ol_store){m,rd,erase,body,mark};}
static void init(ol_ledger *l){assert(ol_init(l,store(&a),store(&b))==OL_OK);}
static const uint8_t digest[32]={1,2,3},wrong[32]={2};
static ol_record snapshot(ol_ledger *l){ol_record r;assert(ol_snapshot(l,&r)==OL_OK);return r;}
static void seed(ol_ledger *l){
 memset(&a,255,sizeof a);memset(&b,255,sizeof b);event=cut=prefix=0;read_failure=false;
 init(l);assert(ol_boot(l)==OL_UNPROVISIONED);assert(ol_provision(l)==OL_OK);
 assert(ol_provision(l)==OL_NOT_EMPTY);assert(ol_boot(l)==OL_OK);
 assert(snapshot(l).boot_epoch==1);
}
static void normal(void){
 ol_ledger l;seed(&l);uint64_t id=0;
 assert(ol_reserve(&l,digest,8,&id)==OL_OK&&id==1);
 assert(ol_reserve(&l,digest,8,&id)==OL_STATE);
 assert(ol_finish(&l,2,digest,8,OL_SEALED)==OL_MISMATCH);
 assert(ol_finish(&l,id,wrong,8,OL_SEALED)==OL_MISMATCH);
 assert(ol_finish(&l,id,digest,9,OL_SEALED)==OL_MISMATCH);
 assert(ol_finish(&l,id,digest,8,OL_SEALED)==OL_OK);
 init(&l);assert(ol_boot(&l)==OL_OK);
 ol_record r=snapshot(&l);assert(r.boot_epoch==2&&r.operation_id==1&&r.state==OL_SEALED);
 assert(ol_reserve(&l,digest,8,&id)==OL_OK&&id==2);
 init(&l);assert(ol_boot(&l)==OL_OK);r=snapshot(&l);
 assert(r.boot_epoch==3&&r.operation_id==2&&r.state==OL_INTERRUPTED);
 assert(ol_finish(&l,id,digest,8,OL_SEALED)==OL_STATE);
 assert(ol_reserve(&l,digest,8,&id)==OL_OK&&id==3);
 assert(ol_finish(&l,id,digest,8,OL_CANCELLED)==OL_OK);
}
static unsigned faults(void){
 unsigned tests=0;
 for(unsigned phase=0;phase<3;phase++){
  for(unsigned step=1;step<=3;step++){
   unsigned max=step==1?OL_FRAME_SIZE:step==2?OL_BODY_SIZE:1;
   for(unsigned n=0;n<=max;n++){
    ol_ledger l;seed(&l);uint64_t id=0;
    if(phase)assert(ol_reserve(&l,digest,8,&id)==OL_OK);
    event=0;cut=step;prefix=n;
    ol_result rc=phase==0?ol_reserve(&l,digest,8,&id):
      phase==1?ol_finish(&l,id,digest,8,OL_SEALED):ol_boot(&l);
    assert(rc==OL_IO);
    ol_record r;assert(ol_snapshot(&l,&r)==OL_STATE);
    if(phase==0)assert(id==0);
    cut=0;init(&l);rc=ol_boot(&l);
    if(rc==OL_OK){
      r=snapshot(&l);
      assert(r.operation_id<2&&r.boot_epoch>=2);
      assert(r.state!=OL_RESERVED);
      if(phase)assert(r.operation_id==1);
      if(r.state==OL_SEALED)assert(phase==1&&step==3&&n==1);
      uint64_t prior=r.operation_id;
      assert(ol_reserve(&l,digest,8,&id)==OL_OK&&id==prior+1);
    }else{assert(rc==OL_CORRUPT);assert(ol_snapshot(&l,&r)==OL_STATE);}
    tests++;
   }
  }
 }
 return tests;
}
int main(void){
 normal();unsigned n=faults();
 ol_ledger l;seed(&l);read_failure=true;assert(ol_boot(&l)==OL_IO);read_failure=false;
 seed(&l);a=b;assert(ol_boot(&l)==OL_CORRUPT);
 seed(&l);b.bytes[20]^=1;assert(ol_boot(&l)==OL_CORRUPT);
 printf("PASS: %u interrupted ledger mutations, boot epoch, high-water reservation, terminal binding, corrupt/ambiguous records and read failures\n",n);
 return 0;
}
