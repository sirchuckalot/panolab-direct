/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "manifest_store.h"
#include "build/fixtures.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

/*
 * The dedicated metadata sector is a proposal pending acceptance. The caller
 * owns slot protection, serializes access, and must successfully invalidate
 * metadata before writing the raw image. The caller verifies raw image readback
 * against the exact manifest before publishing it. The program callback splits
 * requests at device page boundaries.
 */

enum { PAGE_SIZE = 64, HEADER_SIZE = PL_MANIFEST_STORE_OVERHEAD - 1 };

struct nor {
    uint8_t bytes[PL_MANIFEST_STORE_FULL_CAPACITY];
    size_t erase_limit;
    size_t program_limit;
    size_t programmed;
    size_t reads;
    size_t fail_read;
    size_t flip_read_offset;
    uint8_t marker_mask;
    uint8_t image;
    int reverse_erase;
    int leave_marker;
    int erase_error;
};

static int nor_read(void *context, size_t offset, uint8_t *bytes, size_t count)
{
    struct nor *nor = context;
    assert(offset <= sizeof(nor->bytes) && count <= sizeof(nor->bytes) - offset);
    if (++nor->reads == nor->fail_read) {
        memset(bytes, 0x5a, count);
        return -1;
    }
    memcpy(bytes, nor->bytes + offset, count);
    if (nor->flip_read_offset >= offset && nor->flip_read_offset - offset < count)
        bytes[nor->flip_read_offset - offset] ^= 1u;
    return 0;
}

static int nor_erase(void *context)
{
    struct nor *nor = context;
    for (size_t i = 0; i < nor->erase_limit; ++i) {
        size_t offset = nor->reverse_erase ? sizeof(nor->bytes) - 1u - i : i;
        if (offset != 0 || !nor->leave_marker)
            nor->bytes[offset] = 0xff;
    }
    return nor->erase_error ? -1 : 0;
}

static int nor_program(void *context, size_t offset, const uint8_t *bytes, size_t count)
{
    struct nor *nor = context;
    assert(offset <= sizeof(nor->bytes) && count <= sizeof(nor->bytes) - offset);
    if (offset != 0)
        assert(nor->bytes[0] == 0xff);
    else
        assert(count == 1 && bytes[0] == 0);

    while (count != 0) {
        size_t chunk = PAGE_SIZE - offset % PAGE_SIZE;
        if (chunk > count)
            chunk = count;
        for (size_t i = 0; i < chunk; ++i) {
            if (nor->programmed == nor->program_limit)
                return -1;
            uint8_t requested = bytes[i];
            if (offset == 0)
                requested |= nor->marker_mask;
            nor->bytes[offset + i] &= requested;
            ++nor->programmed;
        }
        offset += chunk;
        bytes += chunk;
        count -= chunk;
    }
    return nor->programmed == nor->program_limit ? -1 : 0;
}

static struct pl_manifest_store store_for(struct nor *nor)
{
    return (struct pl_manifest_store) {
        nor, sizeof(nor->bytes), nor_read, nor_erase, nor_program
    };
}

static void expect_load(const struct pl_manifest_store *store,
                        enum pl_manifest_store_result expected,
                        const uint8_t *fixture, size_t length)
{
    struct pl_manifest output;
    unsigned char sentinel[sizeof(output)];
    memset(sentinel, 0xa5, sizeof(sentinel));
    memcpy(&output, sentinel, sizeof(output));
    assert(pl_manifest_store_load(store, &output) == expected);
    if (expected == PL_MANIFEST_STORE_OK) {
        struct pl_manifest parsed;
        assert(pl_manifest_parse(fixture, length, &parsed) == PL_MANIFEST_OK);
        assert(memcmp(output.manifest_sha256, parsed.manifest_sha256, PL_SHA256_SIZE) == 0);
        assert(memcmp(output.image.image_sha256, parsed.image.image_sha256, PL_SHA256_SIZE) == 0);
        assert(output.image.image_length == parsed.image.image_length);
    } else {
        assert(memcmp(&output, sentinel, sizeof(output)) == 0);
    }
}

static void expect_failure(const struct pl_manifest_store *store,
                           enum pl_manifest_store_result expected)
{
    expect_load(store, expected, NULL, 0);
}

static enum pl_manifest_store_result replace_image(const struct pl_manifest_store *store)
{
    struct nor *nor = store->context;
    enum pl_manifest_store_result result = pl_manifest_store_invalidate(store);
    if (result != PL_MANIFEST_STORE_OK)
        return result;

    assert(nor->bytes[0] == 0xff);
    nor->image = 'B';

    struct pl_manifest parsed;
    struct pl_sha256 sha;
    uint8_t digest[PL_SHA256_SIZE];
    assert(pl_manifest_parse(new_manifest, sizeof(new_manifest), &parsed) == PL_MANIFEST_OK);
    pl_sha256_init(&sha);
    assert(pl_sha256_update(&sha, &nor->image, sizeof(nor->image)) == 0);
    pl_sha256_final(&sha, digest);
    assert(parsed.image.image_length == sizeof(nor->image));
    assert(memcmp(parsed.image.image_sha256, digest, sizeof(digest)) == 0);
    return pl_manifest_store_publish(store, new_manifest, sizeof(new_manifest));
}

static void test_erase(const struct nor *old)
{
    for (int reverse = 0; reverse <= 1; ++reverse) {
        for (size_t cut = 0; cut <= sizeof(old->bytes); ++cut) {
            struct nor nor = *old;
            struct pl_manifest_store store = store_for(&nor);
            nor.reverse_erase = reverse;
            nor.erase_limit = cut;
            nor.erase_error = 1;
            assert(replace_image(&store) == PL_MANIFEST_STORE_IO);
            assert(nor.image == 'A' && nor.programmed == 0);
            if (nor.bytes[0] == 0xff)
                expect_failure(&store, PL_MANIFEST_STORE_UNCOMMITTED);
            else if (memcmp(nor.bytes, old->bytes, sizeof(nor.bytes)) == 0)
                expect_load(&store, PL_MANIFEST_STORE_OK, old_manifest, sizeof(old_manifest));
            else
                expect_failure(&store, PL_MANIFEST_STORE_INVALID);
        }
    }

    struct nor nor = *old;
    struct pl_manifest_store store = store_for(&nor);
    nor.leave_marker = 1;
    assert(replace_image(&store) == PL_MANIFEST_STORE_VERIFY);
    assert(nor.image == 'A' && nor.programmed == 0);

    nor = *old;
    nor.fail_read = 1;
    assert(replace_image(&store) == PL_MANIFEST_STORE_IO);
    assert(nor.bytes[0] == 0xff && nor.image == 'A' && nor.programmed == 0);
}

static void test_program(const struct nor *old)
{
    const size_t complete = HEADER_SIZE + sizeof(new_manifest) + 1u;
    for (size_t cut = 0; cut <= complete; ++cut) {
        struct nor nor = *old;
        struct pl_manifest_store store = store_for(&nor);
        nor.program_limit = cut;
        assert(replace_image(&store) == PL_MANIFEST_STORE_IO);
        assert(nor.image == 'B' && nor.programmed == cut);
        if (cut == complete)
            expect_load(&store, PL_MANIFEST_STORE_OK, new_manifest, sizeof(new_manifest));
        else
            expect_failure(&store, PL_MANIFEST_STORE_UNCOMMITTED);
    }

    /* Any subset of the marker bits can remain set after a torn program. */
    for (unsigned mask = 1; mask < 0xff; ++mask) {
        struct nor nor = *old;
        struct pl_manifest_store store = store_for(&nor);
        nor.marker_mask = (uint8_t)mask;
        nor.program_limit = complete;
        assert(replace_image(&store) == PL_MANIFEST_STORE_IO);
        assert(nor.bytes[0] == mask);
        expect_failure(&store, PL_MANIFEST_STORE_UNCOMMITTED);
    }
}

static void test_publish_reads(const struct nor *old)
{
    struct nor committed = *old;
    struct pl_manifest_store store = store_for(&committed);
    assert(replace_image(&store) == PL_MANIFEST_STORE_OK);
    assert(committed.image == 'B');
    const size_t publish_reads = committed.reads;
    expect_load(&store, PL_MANIFEST_STORE_OK, new_manifest, sizeof(new_manifest));

    for (size_t read = 2; read <= publish_reads; ++read) {
        struct nor nor = *old;
        store = store_for(&nor);
        nor.fail_read = read;
        assert(replace_image(&store) == PL_MANIFEST_STORE_IO);
        assert(nor.image == 'B');
        if (read == publish_reads)
            expect_load(&store, PL_MANIFEST_STORE_OK, new_manifest, sizeof(new_manifest));
        else
            expect_failure(&store, PL_MANIFEST_STORE_UNCOMMITTED);
    }

    struct nor torn_marker = *old;
    store = store_for(&torn_marker);
    torn_marker.marker_mask = 0x01;
    assert(replace_image(&store) == PL_MANIFEST_STORE_VERIFY);
    expect_failure(&store, PL_MANIFEST_STORE_UNCOMMITTED);

    const size_t bad_readback[] = { 1, PL_MANIFEST_STORE_OVERHEAD,
                                    PL_MANIFEST_STORE_OVERHEAD + sizeof(new_manifest) - 1u };
    for (size_t i = 0; i < sizeof(bad_readback) / sizeof(bad_readback[0]); ++i) {
        struct nor nor = *old;
        store = store_for(&nor);
        nor.flip_read_offset = bad_readback[i];
        assert(replace_image(&store) == PL_MANIFEST_STORE_VERIFY);
        expect_failure(&store, PL_MANIFEST_STORE_UNCOMMITTED);
    }
}

static void test_corruption(const struct nor *old)
{
    const size_t end = PL_MANIFEST_STORE_OVERHEAD + sizeof(old_manifest);
    for (size_t offset = 1; offset < end; ++offset) {
        struct nor nor = *old;
        struct pl_manifest_store store = store_for(&nor);
        nor.bytes[offset] ^= 1u;
        expect_failure(&store, PL_MANIFEST_STORE_INVALID);
    }

    /* A different canonical body of the same length must fail the digest check. */
    struct nor nor = *old;
    struct pl_manifest_store store = store_for(&nor);
    assert(sizeof(new_manifest) == sizeof(old_manifest));
    memcpy(nor.bytes + PL_MANIFEST_STORE_OVERHEAD, new_manifest, sizeof(new_manifest));
    expect_failure(&store, PL_MANIFEST_STORE_INVALID);

    for (size_t read = 1; read <= 3; ++read) {
        nor = *old;
        nor.fail_read = read;
        expect_failure(&store, PL_MANIFEST_STORE_IO);
    }
}

static void test_capacity_and_arguments(const struct nor *old)
{
    struct nor nor = *old;
    struct pl_manifest_store store = store_for(&nor);
    assert(pl_manifest_store_publish(&store, new_manifest, sizeof(new_manifest)) ==
           PL_MANIFEST_STORE_VERIFY);
    assert(nor.programmed == 0);
    expect_load(&store, PL_MANIFEST_STORE_OK, old_manifest, sizeof(old_manifest));

    assert(pl_manifest_store_invalidate(&store) == PL_MANIFEST_STORE_OK);
    store.capacity = PL_MANIFEST_STORE_OVERHEAD + sizeof(new_manifest) - 1u;
    assert(pl_manifest_store_publish(&store, new_manifest, sizeof(new_manifest)) ==
           PL_MANIFEST_STORE_SIZE);
    assert(pl_manifest_store_publish(&store, new_manifest, 0) == PL_MANIFEST_STORE_SIZE);
    store.capacity = sizeof(nor.bytes) + 1u;
    assert(pl_manifest_store_publish(&store, new_manifest, PL_MANIFEST_MAX_SIZE + 1u) ==
           PL_MANIFEST_STORE_SIZE);
    uint8_t malformed[sizeof(new_manifest)];
    memcpy(malformed, new_manifest, sizeof(malformed));
    malformed[0] = 0xff;
    assert(pl_manifest_store_publish(&store, malformed, sizeof(malformed)) ==
           PL_MANIFEST_STORE_INVALID);
    assert(nor.programmed == 0 && nor.bytes[0] == 0xff);

    store.capacity = PL_MANIFEST_STORE_OVERHEAD + sizeof(new_manifest);
    assert(replace_image(&store) == PL_MANIFEST_STORE_OK);
    expect_load(&store, PL_MANIFEST_STORE_OK, new_manifest, sizeof(new_manifest));
    --store.capacity;
    expect_failure(&store, PL_MANIFEST_STORE_INVALID);
    store.capacity = PL_MANIFEST_STORE_OVERHEAD;
    expect_failure(&store, PL_MANIFEST_STORE_ARGUMENT);
    assert(pl_manifest_store_invalidate(&store) == PL_MANIFEST_STORE_ARGUMENT);
    assert(pl_manifest_store_publish(&store, new_manifest, sizeof(new_manifest)) ==
           PL_MANIFEST_STORE_ARGUMENT);

    store = store_for(&nor);
    assert(pl_manifest_store_load(&store, NULL) == PL_MANIFEST_STORE_ARGUMENT);
    assert(pl_manifest_store_publish(&store, NULL, sizeof(new_manifest)) ==
           PL_MANIFEST_STORE_ARGUMENT);
    store.erase = NULL;
    assert(pl_manifest_store_invalidate(&store) == PL_MANIFEST_STORE_ARGUMENT);
    store.program = NULL;
    assert(pl_manifest_store_publish(&store, new_manifest, sizeof(new_manifest)) ==
           PL_MANIFEST_STORE_ARGUMENT);
    store.read = NULL;
    expect_failure(&store, PL_MANIFEST_STORE_ARGUMENT);
    expect_failure(NULL, PL_MANIFEST_STORE_ARGUMENT);
}

int main(void)
{
    struct nor old = {
        .erase_limit = sizeof(old.bytes),
        .program_limit = SIZE_MAX,
        .flip_read_offset = SIZE_MAX,
        .image = 'A',
    };
    struct pl_manifest_store store = store_for(&old);
    memset(old.bytes, 0xff, sizeof(old.bytes));
    expect_failure(&store, PL_MANIFEST_STORE_UNCOMMITTED);
    assert(pl_manifest_store_invalidate(&store) == PL_MANIFEST_STORE_OK);
    assert(pl_manifest_store_publish(&store, old_manifest, sizeof(old_manifest)) ==
           PL_MANIFEST_STORE_OK);
    expect_load(&store, PL_MANIFEST_STORE_OK, old_manifest, sizeof(old_manifest));
    old.programmed = 0;
    old.reads = 0;

    test_erase(&old);
    test_program(&old);
    test_publish_reads(&old);
    test_corruption(&old);
    test_capacity_and_arguments(&old);
    printf("manifest store checks passed (%zu body bytes, all cut points)\n",
           sizeof(new_manifest));
    return 0;
}
