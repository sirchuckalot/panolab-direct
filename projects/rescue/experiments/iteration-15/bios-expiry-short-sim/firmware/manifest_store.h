/* PanoLab simulated NOR manifest record. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PANOLAB_MANIFEST_STORE_H
#define PANOLAB_MANIFEST_STORE_H

#include "manifest_core.h"

#define PL_MANIFEST_STORE_OVERHEAD (7u + PL_SHA256_SIZE)
#define PL_MANIFEST_STORE_FULL_CAPACITY (PL_MANIFEST_STORE_OVERHEAD + PL_MANIFEST_MAX_SIZE)

/* Offsets are relative to one dedicated erase unit. Operations are synchronous.
 * Return zero only on complete success. Failed mutations may have partial effects.
 */
struct pl_manifest_store {
    void *context;
    size_t capacity;
    int (*read)(void *context, size_t offset, uint8_t *bytes, size_t count);
    int (*erase)(void *context);
    int (*program)(void *context, size_t offset, const uint8_t *bytes, size_t count);
};

enum pl_manifest_store_result {
    PL_MANIFEST_STORE_OK = 0,
    PL_MANIFEST_STORE_ARGUMENT,
    PL_MANIFEST_STORE_SIZE,
    PL_MANIFEST_STORE_IO,
    PL_MANIFEST_STORE_UNCOMMITTED,
    PL_MANIFEST_STORE_INVALID,
    PL_MANIFEST_STORE_VERIFY
};

/* Must succeed before the caller modifies any raw image bytes for this slot. */
enum pl_manifest_store_result pl_manifest_store_invalidate(const struct pl_manifest_store *store);

/* Call only after successful invalidation and verification of raw image readback
 * against this exact manifest. Serialize all access and keep bytes stable.
 */
enum pl_manifest_store_result pl_manifest_store_publish(const struct pl_manifest_store *store,
                                                        const uint8_t *bytes, size_t length);

/* Writes output only when a committed canonical record passes digest validation. */
enum pl_manifest_store_result pl_manifest_store_load(const struct pl_manifest_store *store,
                                                     struct pl_manifest *output);

#endif
