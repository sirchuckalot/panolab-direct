/* PanoLab simulated NOR manifest record. SPDX-License-Identifier: GPL-3.0-or-later */
#include "manifest_store.h"

#define ERASED 0xffu
#define COMMITTED 0x00u
#define HEADER_SIZE (PL_MANIFEST_STORE_OVERHEAD - 1u)
#define DIGEST_OFFSET 6u

static const uint8_t magic[] = { 'P', 'L', 'M', '1' };

static int equal_bytes(const uint8_t *a, const uint8_t *b, size_t count)
{
    for (size_t i = 0; i < count; ++i) {
        if (a[i] != b[i])
            return 0;
    }
    return 1;
}

static int readable(const struct pl_manifest_store *store)
{
    return store && store->read && store->capacity > PL_MANIFEST_STORE_OVERHEAD;
}

static int fits(const struct pl_manifest_store *store, size_t length)
{
    return length != 0 && length <= PL_MANIFEST_MAX_SIZE &&
           length <= store->capacity - PL_MANIFEST_STORE_OVERHEAD;
}

enum pl_manifest_store_result pl_manifest_store_invalidate(const struct pl_manifest_store *store)
{
    uint8_t marker;
    if (!readable(store) || !store->erase)
        return PL_MANIFEST_STORE_ARGUMENT;
    if (store->erase(store->context) || store->read(store->context, 0, &marker, 1))
        return PL_MANIFEST_STORE_IO;
    return marker == ERASED ? PL_MANIFEST_STORE_OK : PL_MANIFEST_STORE_VERIFY;
}

enum pl_manifest_store_result pl_manifest_store_publish(const struct pl_manifest_store *store,
                                                        const uint8_t *bytes, size_t length)
{
    uint8_t marker;
    uint8_t header[HEADER_SIZE];
    uint8_t readback[64];
    struct pl_manifest parsed;

    if (!readable(store) || !store->program || !bytes)
        return PL_MANIFEST_STORE_ARGUMENT;
    if (!fits(store, length))
        return PL_MANIFEST_STORE_SIZE;
    if (pl_manifest_parse(bytes, length, &parsed) != PL_MANIFEST_OK)
        return PL_MANIFEST_STORE_INVALID;
    if (store->read(store->context, 0, &marker, 1))
        return PL_MANIFEST_STORE_IO;
    if (marker != ERASED)
        return PL_MANIFEST_STORE_VERIFY;

    for (size_t i = 0; i < sizeof(magic); ++i)
        header[i] = magic[i];
    header[4] = (uint8_t)(length >> 8);
    header[5] = (uint8_t)length;
    for (size_t i = 0; i < PL_SHA256_SIZE; ++i)
        header[DIGEST_OFFSET + i] = parsed.manifest_sha256[i];

    if (store->program(store->context, 1, header, sizeof(header)) ||
        store->program(store->context, PL_MANIFEST_STORE_OVERHEAD, bytes, length) ||
        store->read(store->context, 1, readback, sizeof(header)))
        return PL_MANIFEST_STORE_IO;
    if (!equal_bytes(header, readback, sizeof(header)))
        return PL_MANIFEST_STORE_VERIFY;
    for (size_t done = 0; done < length;) {
        size_t count = length - done;
        if (count > sizeof(readback))
            count = sizeof(readback);
        if (store->read(store->context, PL_MANIFEST_STORE_OVERHEAD + done, readback, count))
            return PL_MANIFEST_STORE_IO;
        if (!equal_bytes(bytes + done, readback, count))
            return PL_MANIFEST_STORE_VERIFY;
        done += count;
    }

    marker = COMMITTED;
    if (store->program(store->context, 0, &marker, 1) ||
        store->read(store->context, 0, &marker, 1))
        return PL_MANIFEST_STORE_IO;
    return marker == COMMITTED ? PL_MANIFEST_STORE_OK : PL_MANIFEST_STORE_VERIFY;
}

enum pl_manifest_store_result pl_manifest_store_load(const struct pl_manifest_store *store,
                                                     struct pl_manifest *output)
{
    uint8_t marker;
    uint8_t header[HEADER_SIZE];
    uint8_t bytes[PL_MANIFEST_MAX_SIZE];
    struct pl_manifest parsed;
    size_t length;

    if (!readable(store) || !output)
        return PL_MANIFEST_STORE_ARGUMENT;
    if (store->read(store->context, 0, &marker, 1))
        return PL_MANIFEST_STORE_IO;
    if (marker != COMMITTED)
        return PL_MANIFEST_STORE_UNCOMMITTED;
    if (store->read(store->context, 1, header, sizeof(header)))
        return PL_MANIFEST_STORE_IO;
    length = ((size_t)header[4] << 8) | header[5];
    if (!equal_bytes(magic, header, sizeof(magic)) || !fits(store, length))
        return PL_MANIFEST_STORE_INVALID;
    if (store->read(store->context, PL_MANIFEST_STORE_OVERHEAD, bytes, length))
        return PL_MANIFEST_STORE_IO;
    if (pl_manifest_parse(bytes, length, &parsed) != PL_MANIFEST_OK ||
        !equal_bytes(parsed.manifest_sha256, header + DIGEST_OFFSET, PL_SHA256_SIZE))
        return PL_MANIFEST_STORE_INVALID;
    /* Explicit field copy avoids requiring a freestanding memcpy. */
    output->image.profile = parsed.image.profile;
    output->image.manifest_version = parsed.image.manifest_version;
    output->image.role = parsed.image.role;
    output->image.target.board = parsed.image.target.board;
    output->image.target.revision = parsed.image.target.revision;
    output->image.target.fpga = parsed.image.target.fpga;
    output->image.target.bsp_version = parsed.image.target.bsp_version;
    output->image.rescue_api_major = parsed.image.rescue_api_major;
    output->image.rescue_api_min_minor = parsed.image.rescue_api_min_minor;
    output->image.format = parsed.image.format;
    output->image.required_features = parsed.image.required_features;
    output->image.image_length = parsed.image.image_length;
    for (size_t i = 0; i < PL_SHA256_SIZE; ++i) {
        output->image.image_sha256[i] = parsed.image.image_sha256[i];
        output->manifest_sha256[i] = parsed.manifest_sha256[i];
    }
    return PL_MANIFEST_STORE_OK;
}
