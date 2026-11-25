#ifndef RESCUE_FLASH_TRANSACTION_H
#define RESCUE_FLASH_TRANSACTION_H

#include "../storage-core/rescue_storage.h"
#include "../journal-core/rescue_journal.h"
#include "../image-core/image_core.h"

/* Byte offsets refer to the supplied layout. Erase and program operate on
 * one whole aligned sector and page, respectively. Return zero on success,
 * after the operation completes. A failing write may have modified its range.
 */
struct rescue_flash_io {
    void *context;
    int (*read)(void *context, uint32_t offset, uint8_t *data, size_t length);
    int (*erase)(void *context, uint32_t offset);
    int (*program)(void *context, uint32_t offset,
                   const uint8_t *data, size_t length);
};

struct rescue_flash_stage_request {
    const struct rescue_flash_geometry *geometry;
    const struct rescue_region *regions;
    size_t region_count;
    const struct rescue_journal_record *expected;
    enum rescue_slot active; /* NONE while running Rescue. */
    enum rescue_slot target; /* Explicit selection, including first staging. */
    const struct pl_image_metadata *metadata;
    const struct pl_image_policy *policy;
    uint64_t raw_length;
    pl_image_read_fn read_image;
    void *image_context;
};

struct rescue_flash_verified {
    enum rescue_slot slot;
    uint64_t image_length;
    uint8_t digest[PL_SHA256_SIZE];
};

enum rescue_flash_result {
    RESCUE_FLASH_OK = 0,
    RESCUE_FLASH_ARGUMENT,
    RESCUE_FLASH_LAYOUT,
    RESCUE_FLASH_JOURNAL,
    RESCUE_FLASH_STALE,
    RESCUE_FLASH_PROTECTED,
    RESCUE_FLASH_IMAGE,
    RESCUE_FLASH_IO,
    RESCUE_FLASH_READBACK
};

/* The caller holds exclusive access to flash, journal and boot state
 * throughout this call, and keeps the request and source bytes stable.
 * The source must be repeatable and independent of the destination writes.
 * Only success updates verified. Failure after erase can leave the target
 * incomplete. This API never updates the journal or selects a boot slot.
 */
enum rescue_flash_result rescue_flash_stage(
    const struct rescue_flash_io *io,
    const struct rescue_flash_stage_request *request,
    struct rescue_flash_verified *verified);

#endif
