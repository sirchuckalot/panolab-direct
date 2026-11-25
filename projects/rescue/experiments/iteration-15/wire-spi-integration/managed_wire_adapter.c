/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "managed_wire_adapter.h"
#include "../managed-stream/managed_stream.h"
static void progress(const struct wire_session *s,struct mw_progress *p) {
 p->state=s->state; p->next_offset=s->offset;
 p->has_next_offset=s->state==MW_STATE_OPEN || s->state==MW_STATE_SEALED;
}
static enum mw_code status(void *ctx,struct mw_progress *p) {
 struct wire_session *s=ctx;
 if(s->locked)return MW_INTERNAL;
 progress(s,p);return MW_OK;
}
static enum mw_code translate(struct wire_session *s,enum pl_upload_result r,struct mw_progress *p) {
 switch(r) {
 case PL_UPLOAD_OK:progress(s,p);return MW_OK;
 case PL_UPLOAD_OFFSET:case PL_UPLOAD_BUSY:progress(s,p);return MW_CONFLICT;
 case PL_UPLOAD_STALE:return MW_NOT_FOUND;
 case PL_UPLOAD_REJECTED:case PL_UPLOAD_MANIFEST:return MW_REJECTED;
 case PL_UPLOAD_LOCKED:case PL_UPLOAD_BACKEND_ERROR:
    /* Conservatively require recovery even if backend cleanup succeeded. */
    s->locked=1;return MW_INTERNAL;
 case PL_UPLOAD_ARGUMENT:case PL_UPLOAD_LENGTH:case PL_UPLOAD_DIGEST:
    if(s->state==MW_STATE_OPEN)s->state=MW_STATE_CANCELLED;
    return MW_REJECTED;
 default:s->locked=1;return MW_INTERNAL;
 }
}
static enum mw_code begin(void *ctx,uint32_t id,uint32_t seq,const uint8_t *m,size_t n,struct mw_progress *p) {
 struct wire_session *s=ctx;
 if(s->locked)return MW_INTERNAL;
 if(!id || id<=s->id)return MW_NOT_FOUND;
 if(s->state==MW_STATE_OPEN){progress(s,p);return MW_CONFLICT;}
 enum pl_upload_result r=pl_managed_begin(id,seq,m,n);
 if(r!=PL_UPLOAD_BUSY && r!=PL_UPLOAD_STALE) {s->id=id;s->offset=0;s->state=MW_STATE_IDLE;}
 if(r==PL_UPLOAD_OK)s->state=MW_STATE_OPEN;
 return translate(s,r,p);
}
static enum mw_code chunk(void *ctx,uint32_t id,uint32_t off,const uint8_t *b,size_t n,struct mw_progress *p) {
 struct wire_session *s=ctx;
 if(s->locked)return MW_INTERNAL;
 if(id!=s->id || s->state!=MW_STATE_OPEN)return MW_NOT_FOUND;
 enum pl_upload_result r=pl_managed_append(id,off,b,n);
 if(r==PL_UPLOAD_OK)s->offset+=(uint32_t)n;
 return translate(s,r,p);
}
static enum mw_code seal(void *ctx,uint32_t id,struct mw_progress *p) {
 struct wire_session *s=ctx;
 if(s->locked)return MW_INTERNAL;
 if(id!=s->id || s->state!=MW_STATE_OPEN)return MW_NOT_FOUND;
 enum pl_upload_result r=pl_managed_seal(id);
 if(r==PL_UPLOAD_OK)s->state=MW_STATE_SEALED;
 return translate(s,r,p);
}
static enum mw_code cancel(void *ctx,uint32_t id,struct mw_progress *p) {
 struct wire_session *s=ctx;
 if(s->locked)return MW_INTERNAL;
 if(id!=s->id || s->state!=MW_STATE_OPEN)return MW_NOT_FOUND;
 enum pl_upload_result r=pl_managed_cancel(id);
 if(r==PL_UPLOAD_OK)s->state=MW_STATE_CANCELLED;
 return translate(s,r,p);
}
const struct mw_callbacks managed_wire_callbacks={begin,chunk,seal,cancel,status};
