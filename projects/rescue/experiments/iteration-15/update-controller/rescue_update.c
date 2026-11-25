/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "rescue_update.h"
struct unit { const struct rescue_update *u; uint32_t base,size; };
struct session { rescue_return_verifier verify_return; void *return_context; const struct rescue_update *u; struct rescue_region raw[8]; struct unit meta[2],state[2],image[2]; };
static bool eq(const uint8_t *a,const uint8_t *b,size_t n) {
 for(size_t i=0;i<n;i++) if(a[i]!=b[i]) return false;
 return true;
}
static int init(struct session *s,const struct rescue_update *u) {
 if(!u || !u->flash || !u->flash->read || !u->flash->erase || !u->flash->program ||
    !u->policy || !u->identity_verified || !u->in_rescue || u->count>8 ||
    !rescue_layout_valid(u->geometry,u->regions,u->count) ||
    u->geometry->page_size!=256 || u->geometry->erase_size<PL_MANIFEST_STORE_FULL_CAPACITY) return -1;
 s->u=u;
 for(size_t i=0;i<u->count;i++) {
  s->raw[i]=u->regions[i];
  struct rescue_region *r=&s->raw[i];
  if(r->role==RESCUE_REGION_APP_A || r->role==RESCUE_REGION_APP_B) {
   unsigned j=r->role==RESCUE_REGION_APP_A?0u:1u;
   if(r->length<=u->geometry->erase_size) return -1;
   r->length-=u->geometry->erase_size;
   s->meta[j]=(struct unit){u,r->offset+r->length,u->geometry->erase_size};
   s->image[j]=(struct unit){u,r->offset,r->length};
  } else if(r->role==RESCUE_REGION_STATE_0 || r->role==RESCUE_REGION_STATE_1) {
   unsigned j=r->role==RESCUE_REGION_STATE_0?0u:1u;
   s->state[j]=(struct unit){u,r->offset,r->length};
  }
 }
 return rescue_layout_valid(u->geometry,s->raw,u->count)?0:-1;
}
static int unit_read(void *ctx,size_t off,uint8_t *data,size_t len) {
 struct unit *p=ctx;
 if(off>p->size || len>p->size-off) return -1;
 return p->u->flash->read(p->u->flash->context,p->base+(uint32_t)off,data,len);
}
static int unit_erase(void *ctx) {
 struct unit *p=ctx;
 if(p->size!=p->u->geometry->erase_size) return -1;
 return p->u->flash->erase(p->u->flash->context,p->base);
}
/* Preserve surrounding bytes. Physical repeated page programming unqualified. */
static int unit_program(void *ctx,size_t off,const uint8_t *data,size_t len) {
 struct unit *p=ctx; uint8_t page[256];
 if(off>p->size || len>p->size-off) return -1;
 while(len) {
  size_t base=off-off%sizeof page,index=off-base,n=sizeof page-index;
  if(n>len) n=len;
  if(unit_read(p,base,page,sizeof page)) return -1;
  for(size_t i=0;i<n;i++) {
   if((page[index+i]&data[i])!=data[i]) return -1;
   page[index+i]=data[i];
  }
  if(p->u->flash->program(p->u->flash->context,p->base+(uint32_t)base,page,sizeof page)) return -1;
  off+=n; data+=n; len-=n;
 }
 return 0;
}
static int jr(void *ctx,unsigned sector,size_t off,uint8_t *data,size_t len) {
 struct session *s=ctx; return sector<2?unit_read(&s->state[sector],off,data,len):-1;
}
static int je(void *ctx,unsigned sector) {
 struct session *s=ctx; return sector<2?unit_erase(&s->state[sector]):-1;
}
static int jp(void *ctx,unsigned sector,size_t off,const uint8_t *data,size_t len) {
 struct session *s=ctx; return sector<2?unit_program(&s->state[sector],off,data,len):-1;
}
static struct rescue_journal_io journal(struct session *s) {
 return (struct rescue_journal_io){s,s->u->geometry->erase_size,jr,je,jp};
}
static struct pl_manifest_store store(struct session *s,unsigned i) {
 return (struct pl_manifest_store){&s->meta[i],s->meta[i].size,unit_read,unit_erase,unit_program};
}
static size_t image_read(void *ctx,uint64_t off,uint8_t *data,size_t len) {
 struct unit *p=ctx;
 if(off>p->size || len>p->size-off) return 0;
 return unit_read(p,(size_t)off,data,len)?0:len;
}
static bool verify_session(void *ctx,const struct rescue_journal_binding *binding) {
 struct session *s=ctx;
 if(!binding || (binding->slot!=RESCUE_JOURNAL_A && binding->slot!=RESCUE_JOURNAL_B)) return false;
 unsigned i=binding->slot==RESCUE_JOURNAL_A?0u:1u;
 struct pl_manifest_store st=store(s,i); struct pl_manifest m;
 if(pl_manifest_store_load(&st,&m)!=PL_MANIFEST_STORE_OK ||
    !eq(m.manifest_sha256,binding->digest,32) || m.image.image_length>s->image[i].size) return false;
 return pl_image_verify(&m.image,s->u->policy,m.image.image_length,image_read,&s->image[i])==PL_IMAGE_OK;
}
bool rescue_update_verify(const struct rescue_update *u,const struct rescue_journal_binding *binding) {
 struct session s; return init(&s,u)==0 && verify_session(&s,binding);
}
enum update_result rescue_update_stage(const struct rescue_update *u,
 const struct rescue_journal_record *expected,enum rescue_slot target,
 const uint8_t *manifest,size_t manifest_length,uint64_t raw_length,
 pl_image_read_fn read,void *context,struct rescue_journal_binding *binding) {
 struct session s; struct pl_manifest m; struct rescue_journal_record head;
 uint8_t a[RESCUE_JOURNAL_RECORD_BYTES],b[RESCUE_JOURNAL_RECORD_BYTES];
 if(init(&s,u) || !binding || !expected || !read ||
    (target!=RESCUE_SLOT_A && target!=RESCUE_SLOT_B)) return UPDATE_INVALID;
 unsigned i=target==RESCUE_SLOT_A?0u:1u;
 uint8_t slot=(uint8_t)(i==0?RESCUE_JOURNAL_A:RESCUE_JOURNAL_B);
 struct rescue_journal_io j=journal(&s);
 if(rescue_journal_read(&j,&head)!=RESCUE_JOURNAL_OK ||
    rescue_journal_encode(&head,a)!=RESCUE_JOURNAL_OK ||
    rescue_journal_encode(expected,b)!=RESCUE_JOURNAL_OK) return UPDATE_JOURNAL;
 if(!eq(a,b,sizeof a)) return UPDATE_STALE;
 if(head.pending.slot!=RESCUE_JOURNAL_NONE || head.confirmed.slot==slot ||
    head.previous.slot==slot) return UPDATE_PROTECTED;
 if(pl_manifest_parse(manifest,manifest_length,&m)!=PL_MANIFEST_OK ||
    raw_length>s.image[i].size ||
    pl_image_verify(&m.image,u->policy,raw_length,read,context)!=PL_IMAGE_OK) return UPDATE_IMAGE;
 struct pl_manifest_store st=store(&s,i);
 if(pl_manifest_store_invalidate(&st)!=PL_MANIFEST_STORE_OK) return UPDATE_METADATA;
 struct rescue_flash_stage_request req={u->geometry,s.raw,u->count,expected,
   RESCUE_SLOT_NONE,target,&m.image,u->policy,raw_length,read,context};
 struct rescue_flash_verified verified;
 enum rescue_flash_result staged=rescue_flash_stage(u->flash,&req,&verified);
 switch(staged) {
 case RESCUE_FLASH_OK: break;
 case RESCUE_FLASH_STALE: return UPDATE_STALE;
 case RESCUE_FLASH_JOURNAL: return UPDATE_JOURNAL;
 case RESCUE_FLASH_PROTECTED: return UPDATE_PROTECTED;
 case RESCUE_FLASH_IMAGE: return UPDATE_IMAGE;
 case RESCUE_FLASH_ARGUMENT: case RESCUE_FLASH_LAYOUT: return UPDATE_INVALID;
 default: return UPDATE_IO;
 }
 if(pl_manifest_store_publish(&st,manifest,manifest_length)!=PL_MANIFEST_STORE_OK) return UPDATE_METADATA;
 struct rescue_journal_binding result={slot,{0}};
 for(size_t k=0;k<32;k++) result.digest[k]=m.manifest_sha256[k];
 if(!verify_session(&s,&result)) return UPDATE_METADATA;
 *binding=result;
 return UPDATE_OK;
}
enum rescue_trial_result rescue_update_prepare(const struct rescue_update *u,
 uint64_t seq,const struct rescue_journal_binding *binding) {
 struct session s; if(init(&s,u)) return RESCUE_TRIAL_INVALID;
 struct rescue_journal_io j=journal(&s); struct rescue_trial t={&j,&s,verify_session,NULL};
 return rescue_trial_prepare(&t,seq,binding,false);
}
enum rescue_trial_result rescue_update_start(const struct rescue_update *u,uint64_t seq,struct rescue_trial_launch *launch) {
 struct session s; if(init(&s,u)) return RESCUE_TRIAL_INVALID;
 struct rescue_journal_io j=journal(&s); struct rescue_trial t={&j,&s,verify_session,NULL};
 return rescue_trial_start(&t,seq,launch);
}

static bool check_return(void *ctx,const void *evidence,const struct rescue_trial_launch *claim) {
 struct session *s=ctx;
 return s->verify_return && s->verify_return(s->return_context,evidence,claim);
}
enum rescue_trial_result rescue_update_confirm(const struct rescue_update *u,const struct rescue_trial_launch *claim,const void *evidence,bool approved,rescue_return_verifier verifier,void *context) {
 struct session s; if(init(&s,u) || !verifier) return RESCUE_TRIAL_CONFIRM_REJECTED;
 s.verify_return=verifier; s.return_context=context;
 struct rescue_journal_io j=journal(&s); struct rescue_trial t={&j,&s,verify_session,check_return};
 return rescue_trial_confirm(&t,claim,evidence,approved);
}
enum rescue_trial_result rescue_update_failed_reset(const struct rescue_update *u,uint64_t seq) {
 struct session s; if(init(&s,u)) return RESCUE_TRIAL_INVALID;
 struct rescue_journal_io j=journal(&s); struct rescue_trial t={&j,&s,verify_session,NULL};
 return rescue_trial_failed_reset(&t,seq);
}
enum rescue_trial_result rescue_update_rollback(const struct rescue_update *u,uint64_t seq) {
 struct session s; if(init(&s,u)) return RESCUE_TRIAL_INVALID;
 struct rescue_journal_io j=journal(&s); struct rescue_trial t={&j,&s,verify_session,NULL};
 return rescue_trial_rollback(&t,seq);
}
