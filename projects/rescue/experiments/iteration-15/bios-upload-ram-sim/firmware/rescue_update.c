/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "managed_stream.h"
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

/* Streaming backend for simulated NOR. Reuse the controller's private
 * layout, journal, manifest store and bounded raw read adapters above.
 */
static struct {
    struct pl_upload_session upload;
    struct pl_stream_slot slot;
    uint8_t headers[2][RESCUE_JOURNAL_RECORD_BYTES];
    bool initialized;
    bool calling;
    bool locked;
} managed;

static bool managed_headers(struct session *s, bool capture)
{
    uint8_t header[RESCUE_JOURNAL_RECORD_BYTES];
    bool same = true;

    for (unsigned i = 0; i < 2; ++i) {
        if (jr(s, i, 0, header, sizeof header))
            return false;
        if (capture) {
            for (size_t n = 0; n < sizeof header; ++n)
                managed.headers[i][n] = header[n];
        } else if (!eq(header, managed.headers[i], sizeof header)) {
            same = false;
            /* A later scan cannot undo the observed loss of ownership. */
            managed.locked = true;
        }
    }
    return same;
}

static unsigned stream_index(const struct pl_stream_slot *slot)
{
    return slot->target == RESCUE_SLOT_A ? 0u : 1u;
}

static uint8_t stream_journal_slot(const struct pl_stream_slot *slot)
{
    return slot->target == RESCUE_SLOT_A ? RESCUE_JOURNAL_A : RESCUE_JOURNAL_B;
}

/* Mirrors the compatibility checks in pl_image_verify. At begin there
 * are no raw bytes yet. Seal uses pl_image_verify on actual flash reads.
 */
static bool stream_compatible(const struct pl_image_metadata *m,
                              const struct pl_image_policy *p, uint32_t capacity)
{
    return m->profile == PL_TRUSTED_LAN && p->profile == PL_TRUSTED_LAN &&
           m->manifest_version == 1 && m->role == PL_APPLICATION &&
           m->target.board == PL_PANO_G2 && m->target.revision == PL_REV_B &&
           m->target.fpga == PL_XC6SLX150_2_FGG484 &&
           m->target.board == p->detected_target.board &&
           m->target.revision == p->detected_target.revision &&
           m->target.fpga == p->detected_target.fpga &&
           m->target.bsp_version == p->detected_target.bsp_version &&
           m->rescue_api_major == p->rescue_api_major &&
           m->rescue_api_min_minor <= p->rescue_api_minor &&
           m->format == PL_XILINX_SPARTAN6_SPI_V1 &&
           (m->required_features & ~PL_FEATURE_ICAP_RETURN_V1) == 0 &&
           (m->required_features & ~p->supported_features) == 0 &&
           m->image_length != 0 && m->image_length <= p->max_image_length &&
           m->image_length <= capacity; /* uint32_t capacity also bounds SHA length. */
}

static bool stream_read_head(struct pl_stream_slot *slot, struct session *s,
                             struct rescue_journal_record *head)
{
    if (init(s, slot->update))
        return false;
    struct rescue_journal_io j = journal(s);
    uint8_t target = stream_journal_slot(slot);
    return rescue_journal_read(&j, head) == RESCUE_JOURNAL_OK &&
           head->pending.slot == RESCUE_JOURNAL_NONE &&
           head->confirmed.slot != target && head->previous.slot != target;
}

static bool stream_current(struct pl_stream_slot *slot, struct session *s)
{
    struct rescue_journal_record head;
    uint8_t frame[RESCUE_JOURNAL_RECORD_BYTES];
    return stream_read_head(slot, s, &head) &&
           rescue_journal_encode(&head, frame) == RESCUE_JOURNAL_OK &&
           eq(frame, slot->head, sizeof frame) &&
           (slot != &managed.slot || (managed_headers(s, false) && !managed.locked));
}

static enum pl_upload_begin_result stream_begin(void *context, uint64_t id,
    uint64_t expected_sequence, const struct pl_manifest *manifest,
    const uint8_t *bytes, size_t length)
{
    struct pl_stream_slot *slot = context;
    struct session s;
    struct rescue_journal_record head;
    unsigned i = stream_index(slot);

    if (slot->started)
        return PL_UPLOAD_BEGIN_REJECTED;
    slot->binding_valid = false;
    if (!stream_read_head(slot, &s, &head) || head.sequence != expected_sequence ||
        rescue_journal_encode(&head, slot->head) != RESCUE_JOURNAL_OK ||
        !manifest || pl_manifest_parse(bytes, length, &slot->manifest) != PL_MANIFEST_OK ||
        !eq(manifest->manifest_sha256, slot->manifest.manifest_sha256, PL_SHA256_SIZE) ||
        !stream_compatible(&slot->manifest.image, s.u->policy, s.image[i].size) ||
        (slot == &managed.slot && !managed_headers(&s, true)))
        return PL_UPLOAD_BEGIN_REJECTED;

    for (size_t n = 0; n < length; ++n)
        slot->manifest_bytes[n] = bytes[n];
    slot->manifest_length = length;
    slot->received = 0;
    slot->programmed = 0;
    slot->id = id;
    slot->failed = false;
    slot->started = true; /* Even a failed erase may have modified metadata. */
    struct pl_manifest_store st = store(&s, i);
    if (pl_manifest_store_invalidate(&st) != PL_MANIFEST_STORE_OK) {
        slot->failed = true;
        return PL_UPLOAD_BEGIN_ERROR;
    }
    return PL_UPLOAD_BEGIN_OK;
}

static int stream_program_page(struct pl_stream_slot *slot, struct session *s)
{
    struct unit *image = &s->image[stream_index(slot)];
    const struct rescue_flash_io *flash = s->u->flash;
    uint32_t offset = slot->programmed;
    uint32_t address = image->base + offset;

    if (offset > image->size || sizeof slot->page > image->size - offset)
        return -1;
    if (offset % s->u->geometry->erase_size == 0 &&
        flash->erase(flash->context, address))
        return -1;
    if (flash->program(flash->context, address, slot->page, sizeof slot->page))
        return -1;
    slot->programmed += sizeof slot->page;
    return 0;
}

static int stream_append(void *context, uint64_t id, uint64_t offset,
                         const uint8_t *bytes, size_t length)
{
    struct pl_stream_slot *slot = context;
    struct session s;

    if (!slot->started || slot->id != id || slot->failed)
        return -1;
    if (!bytes || !length || length > PL_UPLOAD_MAX_CHUNK ||
        offset != slot->received || length > slot->manifest.image.image_length - offset ||
        !(slot == &managed.slot
          ? init(&s, slot->update) == 0 && managed_headers(&s, false)
          : stream_current(slot, &s))) {
        slot->failed = true;
        return -1;
    }

    while (length) {
        size_t used = slot->received - slot->programmed;
        size_t count = sizeof slot->page - used;
        if (count > length)
            count = length;
        for (size_t n = 0; n < count; ++n)
            slot->page[used + n] = bytes[n];
        slot->received += count;
        bytes += count;
        length -= count;
        if (used + count == sizeof slot->page && stream_program_page(slot, &s)) {
            slot->failed = true;
            return -1;
        }
    }
    return 0;
}

static int stream_seal(void *context, uint64_t id)
{
    struct pl_stream_slot *slot = context;
    struct session s;
    unsigned i = stream_index(slot);
    struct pl_manifest loaded;

    if (!slot->started || slot->id != id || slot->failed)
        return -1;
    slot->failed = true;
    if (slot->received != slot->manifest.image.image_length || !stream_current(slot, &s))
        return -1;

    if (slot->received != slot->programmed) {
        for (size_t n = slot->received - slot->programmed; n < sizeof slot->page; ++n)
            slot->page[n] = 0xff;
        if (stream_program_page(slot, &s))
            return -1;
    }

    struct pl_manifest_store st = store(&s, i);
    if (pl_image_verify(&slot->manifest.image, s.u->policy, slot->received,
                        image_read, &s.image[i]) != PL_IMAGE_OK ||
        pl_manifest_store_publish(&st, slot->manifest_bytes, slot->manifest_length) !=
            PL_MANIFEST_STORE_OK ||
        pl_manifest_store_load(&st, &loaded) != PL_MANIFEST_STORE_OK ||
        !eq(loaded.manifest_sha256, slot->manifest.manifest_sha256, PL_SHA256_SIZE))
        return -1;

    slot->started = false;
    slot->failed = false;
    slot->binding_valid = true;
    return 0;
}

static int stream_abort(void *context, uint64_t id)
{
    struct pl_stream_slot *slot = context;
    struct session s;

    if (!slot->started)
        return 0;
    if (slot->id != id)
        return -1;
    slot->failed = true;
    if (!stream_current(slot, &s))
        return -1;

    struct pl_manifest_store st = store(&s, stream_index(slot));
    if (pl_manifest_store_invalidate(&st) != PL_MANIFEST_STORE_OK)
        return -1;
    slot->started = false;
    return 0;
}

static const struct pl_upload_backend stream_backend = {
    stream_begin, stream_append, stream_seal, stream_abort
};

enum pl_upload_result pl_stream_slot_init(struct pl_upload_session *session,
    struct pl_stream_slot *slot, const struct rescue_update *update,
    enum rescue_slot target, uint64_t last_id)
{
    struct session s;
    if (!session || !slot || (target != RESCUE_SLOT_A && target != RESCUE_SLOT_B) ||
        init(&s, update))
        return PL_UPLOAD_ARGUMENT;

    *slot = (struct pl_stream_slot){.update = update, .target = target};
    return pl_upload_init(session, &stream_backend, slot,
                          s.image[stream_index(slot)].size, last_id);
}

bool pl_stream_slot_binding(const struct pl_stream_slot *slot, uint64_t id,
                            struct rescue_journal_binding *binding)
{
    if (!slot || !binding || !slot->binding_valid || slot->id != id)
        return false;
    binding->slot = stream_journal_slot(slot);
    for (size_t n = 0; n < PL_SHA256_SIZE; ++n)
        binding->digest[n] = slot->manifest.manifest_sha256[n];
    return true;
}

static enum pl_upload_result managed_enter(void)
{
    if (managed.locked)
        return PL_UPLOAD_LOCKED;
    if (managed.calling)
        return PL_UPLOAD_BUSY;
    if (!managed.initialized)
        return PL_UPLOAD_ARGUMENT;
    /* Synchronous flash and verifier callbacks can reenter the facade. */
    managed.calling = true;
    return PL_UPLOAD_OK;
}

static enum pl_upload_result managed_leave(enum pl_upload_result result)
{
    if (result == PL_UPLOAD_LOCKED)
        managed.locked = true;
    managed.calling = false;
    return result;
}

static bool managed_enter_idle(void)
{
    return !managed.slot.started && managed_enter() == PL_UPLOAD_OK;
}

enum pl_upload_result pl_managed_init(const struct rescue_update *update,
    enum rescue_slot target, uint64_t last_id)
{
    if (managed.locked)
        return PL_UPLOAD_LOCKED;
    if (managed.initialized || managed.calling)
        return PL_UPLOAD_BUSY;
    managed.calling = true;
    enum pl_upload_result result = pl_stream_slot_init(&managed.upload,
        &managed.slot, update, target, last_id);
    managed.initialized = result == PL_UPLOAD_OK;
    return managed_leave(result);
}

enum pl_upload_result pl_managed_begin(uint64_t id, uint64_t expected_sequence,
    const uint8_t *manifest, size_t length)
{
    enum pl_upload_result result = managed_enter();
    if (result != PL_UPLOAD_OK)
        return result;
    return managed_leave(pl_upload_begin(&managed.upload, id, expected_sequence,
                                        manifest, length));
}

enum pl_upload_result pl_managed_append(uint64_t id, uint64_t offset,
    const uint8_t *bytes, size_t length)
{
    enum pl_upload_result result = managed_enter();
    if (result != PL_UPLOAD_OK)
        return result;
    return managed_leave(pl_upload_append(&managed.upload, id, offset, bytes, length));
}

enum pl_upload_result pl_managed_seal(uint64_t id)
{
    enum pl_upload_result result = managed_enter();
    if (result != PL_UPLOAD_OK)
        return result;
    return managed_leave(pl_upload_seal(&managed.upload, id));
}

enum pl_upload_result pl_managed_cancel(uint64_t id)
{
    enum pl_upload_result result = managed_enter();
    if (result != PL_UPLOAD_OK)
        return result;
    return managed_leave(pl_upload_cancel(&managed.upload, id));
}

bool pl_managed_binding(uint64_t id, struct rescue_journal_binding *binding)
{
    return managed.initialized && !managed.calling && !managed.locked &&
           !managed.slot.started && pl_stream_slot_binding(&managed.slot, id, binding);
}

enum rescue_journal_result pl_managed_journal_read(struct rescue_journal_record *head)
{
    if (!head || !managed_enter_idle())
        return RESCUE_JOURNAL_INVALID;
    struct session s;
    enum rescue_journal_result result = RESCUE_JOURNAL_INVALID;
    if (init(&s, managed.slot.update) == 0) {
        struct rescue_journal_io j = journal(&s);
        result = rescue_journal_read(&j, head);
    }
    managed.calling = false;
    return result;
}

bool pl_managed_verify(const struct rescue_journal_binding *binding)
{
    if (!managed_enter_idle())
        return false;
    bool result = rescue_update_verify(managed.slot.update, binding);
    managed.calling = false;
    return result;
}

enum rescue_trial_result pl_managed_prepare(uint64_t seq,
    const struct rescue_journal_binding *binding)
{
    if (!managed_enter_idle())
        return RESCUE_TRIAL_INVALID;
    enum rescue_trial_result result = rescue_update_prepare(managed.slot.update, seq, binding);
    managed.calling = false;
    return result;
}

enum rescue_trial_result pl_managed_start(uint64_t seq, struct rescue_trial_launch *launch)
{
    if (!managed_enter_idle())
        return RESCUE_TRIAL_INVALID;
    enum rescue_trial_result result = rescue_update_start(managed.slot.update, seq, launch);
    managed.calling = false;
    return result;
}

enum rescue_trial_result pl_managed_confirm(const struct rescue_trial_launch *claim,
    const void *evidence, bool approved, rescue_return_verifier verifier, void *context)
{
    if (!managed_enter_idle())
        return RESCUE_TRIAL_INVALID;
    enum rescue_trial_result result = rescue_update_confirm(managed.slot.update,
        claim, evidence, approved, verifier, context);
    managed.calling = false;
    return result;
}

enum rescue_trial_result pl_managed_failed_reset(uint64_t seq)
{
    if (!managed_enter_idle())
        return RESCUE_TRIAL_INVALID;
    enum rescue_trial_result result = rescue_update_failed_reset(managed.slot.update, seq);
    managed.calling = false;
    return result;
}

enum rescue_trial_result pl_managed_rollback(uint64_t seq)
{
    if (!managed_enter_idle())
        return RESCUE_TRIAL_INVALID;
    enum rescue_trial_result result = rescue_update_rollback(managed.slot.update, seq);
    managed.calling = false;
    return result;
}
