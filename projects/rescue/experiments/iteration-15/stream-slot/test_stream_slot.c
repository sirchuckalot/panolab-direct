/* Simulated NOR fixture adapted from ../update-controller/test_update.c. */
#include "stream_slot.h"
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

static uint8_t nor[CAP], before[CAP];
static unsigned mutations, fail_at, marker_at, corrupt_reads;
static bool fail_after_write, corrupt_readback;
static struct rescue_journal_record head;
static struct rescue_journal_binding old, expected;
static struct pl_upload_session session;
static struct pl_stream_slot slot;

static int rd(void *ctx, uint32_t off, uint8_t *data, size_t n)
{
    (void)ctx;
    assert(off <= CAP && n <= CAP - off);
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
    size_t limit = fail && !fail_after_write ? n / 2 : n;
    for (size_t i = 0; i < limit; ++i) {
        assert((nor[off + i] & data[i]) == data[i]);
        nor[off + i] &= data[i];
    }
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

static enum pl_upload_result begin(uint64_t id, uint64_t sequence)
{
    return pl_upload_begin(&session, id, sequence, manifest, sizeof manifest);
}

static void no_binding(void)
{
    struct rescue_journal_binding binding;
    assert(!pl_stream_slot_binding(&slot, ID, &binding));
    assert(!rescue_update_verify(&update, &old));
    assert(!rescue_update_verify(&update, &expected));
}

static enum pl_upload_result append_image(const uint8_t *image)
{
    const size_t chunks[] = {19, 266, 227, 1};
    size_t offset = 0;
    for (size_t i = 0; i < sizeof chunks / sizeof chunks[0]; ++i) {
        assert(chunks[i] <= sizeof raw - offset);
        enum pl_upload_result result =
            pl_upload_append(&session, ID, offset, image + offset, chunks[i]);
        if (result != PL_UPLOAD_OK)
            return result;
        offset += chunks[i];
        no_binding();
    }
    assert(offset == sizeof raw);
    return PL_UPLOAD_OK;
}

static unsigned test_success(void)
{
    struct rescue_journal_binding binding;

    seed();
    assert(sizeof raw == sizeof old_raw);
    assert(memcmp(raw, old_raw, sizeof raw) != 0);
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_OK);
    no_binding();
    assert(memcmp(nor + B, old_raw, sizeof old_raw) == 0);
    assert(append_image(raw) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, ID) == PL_UPLOAD_OK);
    assert(!pl_stream_slot_binding(&slot, ID - 1, &binding));
    assert(pl_stream_slot_binding(&slot, ID, &binding));
    assert(binding.slot == expected.slot);
    assert(memcmp(binding.digest, expected.digest, sizeof binding.digest) == 0);
    assert(rescue_update_verify(&update, &binding));
    assert(!rescue_update_verify(&update, &old));
    assert(memcmp(nor + B, raw, sizeof raw) == 0);
    assert(nor[B + sizeof raw] == 0xff);
    assert(marker_at != 0 && marker_at == mutations && nor[M] == 0);
    preserved();
    return mutations;
}

static void unchanged(void)
{
    assert(mutations == 0);
    assert(memcmp(nor, before, sizeof nor) == 0);
}

static void test_rejected(void)
{
    seed();
    assert(begin(ID - 1, SEQUENCE) == PL_UPLOAD_STALE);
    unchanged();
    assert(begin(ID, SEQUENCE - 1) == PL_UPLOAD_REJECTED);
    unchanged();

    seed();
    assert(pl_stream_slot_init(&session, &slot, &update, RESCUE_SLOT_A, ID - 1)
           == PL_UPLOAD_OK);
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_REJECTED);
    unchanged();

    seed();
    head.previous = old;
    assert(rescue_journal_encode(&head, nor + J0) == RESCUE_JOURNAL_OK);
    memcpy(before, nor, sizeof nor);
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_REJECTED);
    unchanged();

    seed();
    struct pl_image_policy wrong = policy;
    wrong.detected_target.bsp_version++;
    update.policy = &wrong;
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_REJECTED);
    unchanged();
    update.policy = &policy;
}

static void test_abort(void)
{
    seed();
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, ID, 0, raw, P + 3) == PL_UPLOAD_OK);
    assert(pl_upload_cancel(&session, ID) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, ID) == PL_UPLOAD_STALE);
    assert(marker_at == 0 && nor[M] == 0xff);
    no_binding();
    preserved();
    assert(begin(ID + 1, SEQUENCE) == PL_UPLOAD_OK);
    assert(pl_upload_cancel(&session, ID + 1) == PL_UPLOAD_OK);
    preserved();

    seed();
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_OK);
    assert(append_image(old_raw) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, ID) == PL_UPLOAD_DIGEST);
    assert(marker_at == 0 && nor[M] == 0xff);
    no_binding();
    preserved();
}

static void test_mutation_failures(unsigned total)
{
    for (unsigned cut = 1; cut <= total; ++cut) {
        for (unsigned completed = 0; completed <= 1; ++completed) {
            seed();
            fail_at = cut;
            fail_after_write = completed != 0;
            enum pl_upload_result result = begin(ID, SEQUENCE);
            if (result == PL_UPLOAD_OK)
                result = append_image(raw);
            if (result == PL_UPLOAD_OK)
                result = pl_upload_seal(&session, ID);
            assert(result == PL_UPLOAD_BACKEND_ERROR);
            assert(mutations == cut + 1);
            if (cut == total)
                assert(marker_at == cut);
            assert(nor[M] == 0xff);
            no_binding();
            preserved();
        }
    }

    seed();
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, ID, 0, raw, P) == PL_UPLOAD_OK);
    fail_at = mutations + 1;
    assert(pl_upload_cancel(&session, ID) == PL_UPLOAD_LOCKED);
    assert(mutations == fail_at);
    assert(begin(ID + 1, SEQUENCE) == PL_UPLOAD_LOCKED);
    assert(mutations == fail_at);
    no_binding();
    preserved();
}

static void test_changed_head(void)
{
    for (unsigned operation = 0; operation < 3; ++operation) {
        seed();
        assert(begin(ID, SEQUENCE) == PL_UPLOAD_OK);
        size_t received = operation == 1 ? sizeof raw : P;
        assert(pl_upload_append(&session, ID, 0, raw, received) == PL_UPLOAD_OK);

        /* Simulate another owner advancing the journal between upload calls. */
        ++head.sequence;
        head.previous = old;
        assert(rescue_journal_encode(&head, nor + J1) == RESCUE_JOURNAL_OK);
        memcpy(before, nor, sizeof nor);
        mutations = 0;

        enum pl_upload_result result;
        if (operation == 0)
            result = pl_upload_append(&session, ID, received, raw + received, P);
        else if (operation == 1)
            result = pl_upload_seal(&session, ID);
        else
            result = pl_upload_cancel(&session, ID);
        assert(result == PL_UPLOAD_LOCKED);
        assert(begin(ID + 1, head.sequence) == PL_UPLOAD_LOCKED);
        no_binding();
        unchanged();
    }

    seed();
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, ID, 0, raw, P) == PL_UPLOAD_OK);
    /* A newer head also invalidates the upload if B stays writable. */
    ++head.sequence;
    assert(rescue_journal_encode(&head, nor + J1) == RESCUE_JOURNAL_OK);
    memcpy(before, nor, sizeof nor);
    mutations = 0;
    assert(pl_upload_append(&session, ID, P, raw + P, P) == PL_UPLOAD_LOCKED);
    assert(pl_upload_cancel(&session, ID) == PL_UPLOAD_LOCKED);
    no_binding();
    unchanged();
}

static void test_readback(void)
{
    seed();
    assert(begin(ID, SEQUENCE) == PL_UPLOAD_OK);
    assert(append_image(raw) == PL_UPLOAD_OK);
    corrupt_readback = true;
    assert(pl_upload_seal(&session, ID) == PL_UPLOAD_BACKEND_ERROR);
    assert(corrupt_reads > 0);
    assert(memcmp(nor + B, raw, sizeof raw) == 0);
    corrupt_readback = false;
    assert(marker_at == 0 && nor[M] == 0xff);
    no_binding();
    preserved();
}

static void test_cross_sector(void)
{
    seed();
    enum { LENGTH = S + 17 };
    uint8_t chunk[PL_UPLOAD_MAX_CHUNK];
    assert(pl_upload_begin(&session, ID, SEQUENCE, large_manifest, sizeof large_manifest) == PL_UPLOAD_OK);
    for (size_t off = 0; off < LENGTH;) {
        size_t n = LENGTH - off;
        if (n > 997) n = 997;
        for (size_t i=0;i<n;i++) chunk[i]=(uint8_t)((off+i)*17+31);
        assert(pl_upload_append(&session, ID, off, chunk, n)==PL_UPLOAD_OK);
        off+=n;
    }
    assert(pl_upload_seal(&session,ID)==PL_UPLOAD_OK);
    struct rescue_journal_binding binding;
    assert(pl_stream_slot_binding(&slot,ID,&binding));
    assert(memcmp(binding.digest,large_digest,32)==0);
    assert(rescue_update_verify(&update,&binding));
    for(size_t i=0;i<LENGTH;i++) assert(nor[B+i]==(uint8_t)(i*17+31));
    for(size_t i=LENGTH;i<2*S;i++) assert(nor[B+i]==0xff);
    preserved();
    printf("PASS: %u-byte cross-sector streaming upload, final-page padding and readback\n",LENGTH);
}

int main(void)
{
    assert(rescue_geometry_lookup(0x202018, &geometry));
    unsigned total = test_success();
    test_rejected();
    test_abort();
    test_mutation_failures(total);
    test_changed_head();
    test_readback();
    test_cross_sector();
    printf("PASS: streaming NOR, %u upload mutation boundaries plus abort, journal safety and readback\n",
           total);
    return 0;
}
