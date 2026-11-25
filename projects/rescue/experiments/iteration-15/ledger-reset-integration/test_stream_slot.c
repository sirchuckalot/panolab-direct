#define _GNU_SOURCE
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
/* Simulated NOR fixture adapted from ../update-controller/test_update.c. */
#include "managed_stream.h"
#include "../operation-ledger/op_ledger.h"
#include "fixtures.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CAP = 16 * 1024 * 1024, S = 256 * 1024, P = 256,
    A = 2 * S, B = 5 * S, M = 7 * S, J0 = 9 * S, J1 = 10 * S,
    SEQUENCE = 8, ID = 21
};

static const struct rescue_region map[] = {
    {RESCUE_REGION_BOOT, 0, S}, {RESCUE_REGION_RESCUE, S, S},
    {RESCUE_REGION_APP_A, A, 3 * S}, {RESCUE_REGION_APP_B, B, 3 * S},
    {RESCUE_REGION_IDENTITY, 8 * S, S}, {RESCUE_REGION_STATE_0, J0, S},
    {RESCUE_REGION_STATE_1, J1, S}, {RESCUE_REGION_RESERVED, 15 * S, S}
};

static uint8_t (*shared_nor)[CAP];
#define nor (*shared_nor)
static uint8_t before[CAP];
static unsigned crash_at;
static bool crash_complete;
static unsigned mutations, fail_at, marker_at, corrupt_reads;
static size_t journal_bytes, journal_headers[2], flash_reads;
static bool fail_after_write, corrupt_readback;
static struct rescue_journal_record head;
static struct rescue_journal_binding old, expected;
static struct pl_upload_session session;
static struct pl_stream_slot slot;

static int rd(void *ctx, uint32_t off, uint8_t *data, size_t n)
{
    (void)ctx;
    assert(off <= CAP && n <= CAP - off);
    ++flash_reads;
    if (off >= J0 && off < J1 + S) {
        journal_bytes += n;
        if (n == RESCUE_JOURNAL_RECORD_BYTES && (off == J0 || off == J1))
            ++journal_headers[off == J1];
    }
    memcpy(data, nor + off, n);
    if (corrupt_readback && off == B && n > 0) {
        data[0] ^= 1;
        ++corrupt_reads;
    }
    return 0;
}

static bool writable(uint32_t off, size_t n)
{
    return off >= B && off <= B + 3 * S && n <= B + 3 * S - off;
}

static int er(void *ctx, uint32_t off)
{
    (void)ctx;
    assert(off % S == 0 && writable(off, S));
    bool fail = ++mutations == fail_at;
    if(mutations==crash_at){memset(nor+off,0xff,crash_complete?S:S/2);_exit(70);}
    memset(nor + off, 0xff, fail && !fail_after_write ? S / 2 : S);
    return fail ? -1 : 0;
}

static int pg(void *ctx, uint32_t off, const uint8_t *data, size_t n)
{
    (void)ctx;
    assert(off % P == 0 && n == P && writable(off, n));
    bool fail = ++mutations == fail_at;
    if (off == M && nor[M] == 0xff && data[0] == 0) {
        assert(marker_at == 0);
        marker_at = mutations;
    }
    size_t limit = mutations==crash_at && !crash_complete?n/2:fail && !fail_after_write ? n/2:n;
    for (size_t i = 0; i < limit; ++i) {
        assert((nor[off + i] & data[i]) == data[i]);
        nor[off + i] &= data[i];
    }
    if(mutations==crash_at)_exit(70);
    return fail ? -1 : 0;
}

static struct rescue_flash_geometry geometry;
static const struct rescue_flash_io flash = {NULL, rd, er, pg};
static const struct pl_image_policy policy = {
    .profile = PL_TRUSTED_LAN,
    .detected_target = {PL_PANO_G2, PL_REV_B, PL_XC6SLX150_2_FGG484, 1},
    .rescue_api_major = 1,
    .max_image_length = 2 * S
};
static struct rescue_update update = {
    &flash, &geometry, map, sizeof map / sizeof map[0], &policy, true, true
};

static void fixture_image(uint32_t base)
{
    memset(nor + base, 0xff, 3 * S);
    memcpy(nor + base, old_raw, sizeof old_raw);
    uint8_t *p = nor + base + 2 * S;
    p[0] = 0;
    memcpy(p + 1, "PLM1", 4);
    p[5] = (uint8_t)(sizeof old_manifest >> 8);
    p[6] = (uint8_t)sizeof old_manifest;
    memcpy(p + 7, old_digest, sizeof old_digest);
    memcpy(p + 39, old_manifest, sizeof old_manifest);
}

static void seed(void)
{
    memset(nor, 0x5a, sizeof nor);
    memset(nor + J0, 0xff, 2 * S);
    fixture_image(A);
    fixture_image(B);
    head = (struct rescue_journal_record){
        .sequence = SEQUENCE, .state = RESCUE_RECORD_STABLE, .reason = "fixture"
    };
    old.slot = expected.slot = RESCUE_JOURNAL_B;
    memcpy(old.digest, old_digest, sizeof old.digest);
    memcpy(expected.digest, digest, sizeof expected.digest);
    head.confirmed = old;
    head.confirmed.slot = RESCUE_JOURNAL_A;
    assert(rescue_journal_encode(&head, nor + J0) == RESCUE_JOURNAL_OK);
    memcpy(before, nor, sizeof nor);
    mutations = fail_at = marker_at = corrupt_reads = 0;
    fail_after_write = corrupt_readback = false;
    assert(pl_stream_slot_init(&session, &slot, &update, RESCUE_SLOT_B, ID - 1)
           == PL_UPLOAD_OK);
    assert(rescue_update_verify(&update, &old));
}

static void preserved(void)
{
    assert(memcmp(nor + J0, before + J0, 2 * S) == 0);
    assert(memcmp(nor, before, B) == 0);
    assert(memcmp(nor + B + 3 * S, before + B + 3 * S, CAP - B - 3 * S) == 0);
}


/* Separate synthetic record stores; no physical partition assigned. */
static uint8_t (*records)[2][OL_FRAME_SIZE];
static ol_read_result lr(void *ctx,uint8_t *out){
 uint8_t *p=ctx;bool empty=true;for(unsigned i=0;i<OL_FRAME_SIZE;i++)if(p[i]!=255)empty=false;
 memcpy(out,p,OL_FRAME_SIZE);return empty?OL_READ_EMPTY:OL_READ_FRAME;
}
static bool le(void *ctx){memset(ctx,255,OL_FRAME_SIZE);return true;}
static bool lb(void *ctx,const uint8_t *data){uint8_t *p=ctx;for(unsigned i=0;i<OL_BODY_SIZE;i++){assert((p[i]&data[i])==data[i]);p[i]&=data[i];}return true;}
static bool lm(void *ctx,uint8_t marker){uint8_t *p=ctx;p[OL_BODY_SIZE]&=marker;return true;}
static void li(ol_ledger *l){ol_store x={(*records)[0],lr,le,lb,lm},y={(*records)[1],lr,le,lb,lm};assert(ol_init(l,x,y)==OL_OK);}
static ol_record boot(ol_ledger *l){ol_record r;li(l);assert(ol_boot(l)==OL_OK);assert(ol_snapshot(l,&r)==OL_OK);return r;}
static void ledger_seed(void){ol_ledger l;memset(records,255,sizeof *records);li(&l);assert(ol_provision(&l)==OL_OK);}
static void child_status(pid_t pid,int expected_status){
 int status=0;assert(pid>0 && waitpid(pid,&status,0)==pid);assert(WIFEXITED(status)&&WEXITSTATUS(status)==expected_status);
}
static void attempt(unsigned cut,bool complete){
 crash_at=cut;crash_complete=complete;
 ol_ledger l;ol_record r=boot(&l);uint64_t id=0;
 assert(r.boot_epoch==1 && r.operation_id==0);
 assert(pl_managed_init(&update,RESCUE_SLOT_B,r.operation_id)==PL_UPLOAD_OK);
 assert(ol_reserve(&l,digest,SEQUENCE,&id)==OL_OK && id==1);
 assert(pl_managed_begin(id,SEQUENCE,manifest,sizeof manifest)==PL_UPLOAD_OK);
 assert(pl_managed_append(id,0,raw,sizeof raw)==PL_UPLOAD_OK);
 assert(pl_managed_seal(id)==PL_UPLOAD_OK);
 struct rescue_journal_binding binding;
 assert(pl_managed_binding(id,&binding)&&pl_managed_verify(&binding));
 assert(ol_finish(&l,id,digest,SEQUENCE,OL_SEALED)==OL_OK);
 _exit(0);
}
static void restart(void){
 ol_ledger l;ol_record r=boot(&l);uint64_t id=0;
 assert(r.boot_epoch==2 && r.operation_id==1 && r.state==OL_INTERRUPTED);
 assert(pl_managed_init(&update,RESCUE_SLOT_B,r.operation_id)==PL_UPLOAD_OK);
 struct rescue_journal_record current;struct rescue_journal_binding binding;
 assert(pl_managed_journal_read(&current)==RESCUE_JOURNAL_OK);
 assert(current.sequence==SEQUENCE && current.confirmed.slot==RESCUE_JOURNAL_A && current.pending.slot==RESCUE_JOURNAL_NONE);
 assert(pl_managed_verify(&current.confirmed));
 assert(!pl_managed_binding(r.operation_id,&binding));
 assert(pl_managed_append(r.operation_id,0,raw,1)==PL_UPLOAD_STALE);
 assert(pl_managed_begin(r.operation_id,SEQUENCE,manifest,sizeof manifest)==PL_UPLOAD_STALE);
 assert(ol_reserve(&l,digest,SEQUENCE,&id)==OL_OK&&id==2);
 assert(pl_managed_begin(id,SEQUENCE,manifest,sizeof manifest)==PL_UPLOAD_OK);
 assert(pl_managed_append(id,0,raw,sizeof raw)==PL_UPLOAD_OK);
 assert(pl_managed_seal(id)==PL_UPLOAD_OK);
 assert(pl_managed_binding(id,&binding)&&pl_managed_verify(&binding));
 assert(ol_finish(&l,id,digest,SEQUENCE,OL_SEALED)==OL_OK);
 _exit(0);
}
static void inspect_after_restart(bool expect_valid){
 ol_ledger l;ol_record r=boot(&l);
 assert(r.boot_epoch==3 && r.operation_id==2 && r.state==OL_SEALED && r.journal_sequence==SEQUENCE);
 assert(memcmp(r.digest,digest,32)==0);
 assert(pl_managed_init(&update,RESCUE_SLOT_B,r.operation_id)==PL_UPLOAD_OK);
 struct rescue_journal_record j;assert(pl_managed_journal_read(&j)==RESCUE_JOURNAL_OK);
 assert(j.sequence==r.journal_sequence && j.confirmed.slot==RESCUE_JOURNAL_A);
 struct rescue_journal_binding candidate={RESCUE_JOURNAL_B,{0}};
 memcpy(candidate.digest,r.digest,32);
 assert(pl_managed_verify(&candidate)==expect_valid);
 assert(pl_managed_verify(&j.confirmed));
 /* Ledger alone is never evidence of current image integrity. No activation. */
 _exit(0);
}
int main(void){
 shared_nor=mmap(NULL,CAP,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);assert(shared_nor!=MAP_FAILED);
 records=mmap(NULL,sizeof *records,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);assert(records!=MAP_FAILED);
 assert(rescue_geometry_lookup(0x202018,&geometry));
 for(unsigned cut=1;cut<=9;cut++)for(unsigned done=0;done<=1;done++){
  seed();ledger_seed();pid_t pid=fork();if(pid==0)attempt(cut,done!=0);child_status(pid,70);
  preserved();assert(rescue_update_verify(&update,&head.confirmed));
  if(rescue_update_verify(&update,&old))assert(memcmp(nor+B,old_raw,sizeof old_raw)==0);
  if(rescue_update_verify(&update,&expected))assert(memcmp(nor+B,raw,sizeof raw)==0);
  if(memcmp(nor+B,old_raw,sizeof old_raw)!=0)assert(!rescue_update_verify(&update,&old));
  pid=fork();if(pid==0)restart();child_status(pid,0);
  preserved();assert(rescue_update_verify(&update,&expected));
 }
 /* Inspect retained terminal record with a fresh process, then corrupt raw data. */
 pid_t inspector=fork();if(inspector==0)inspect_after_restart(true);child_status(inspector,0);
 /* Independent second scenario: rerun interrupted update/restart to reset epoch. */
 seed();ledger_seed();pid_t worker=fork();if(worker==0)attempt(4,true);child_status(worker,70);
 worker=fork();if(worker==0)restart();child_status(worker,0);
 nor[B]^=1;inspector=fork();if(inspector==0)inspect_after_restart(false);child_status(inspector,0);
 preserved();puts("PASS: fresh-process terminal ledger and image reconciliation, corrupted sealed image rejected");
 assert(munmap(shared_nor,CAP)==0);assert(munmap(records,sizeof *records)==0);puts("PASS: 18 abrupt process exits at nine NOR mutations, ledger-backed ID recovery without supplied high-water mark");return 0;
}
