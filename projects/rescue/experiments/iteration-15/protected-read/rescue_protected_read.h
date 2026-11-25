#ifndef RESCUE_PROTECTED_READ_H
#define RESCUE_PROTECTED_READ_H

#include "../storage-core/rescue_storage.h"
#include "../identity-record/identity_record.h"
#include "../journal-core/rescue_journal.h"

typedef int (*rescue_protected_read_fn)(void *context, uint32_t offset,
                                        uint8_t *data, size_t length);

enum rescue_inspection_result {
    RESCUE_INSPECTION_OK = 0,
    RESCUE_INSPECTION_NO_LAYOUT,
    RESCUE_INSPECTION_INVALID
};

enum rescue_persistent_status {
    RESCUE_PERSISTENT_VALID = 0,
    RESCUE_PERSISTENT_MISSING,
    RESCUE_PERSISTENT_CORRUPT,
    RESCUE_PERSISTENT_READ_ERROR
};

struct rescue_persistent_state {
    enum rescue_persistent_status identity_status;
    enum rescue_persistent_status journal_status;
    struct rescue_identity identity;
    struct rescue_journal_record journal;
};

/*
 * Keep the map and flash contents stable throughout inspection. The callback
 * reads an absolute byte range and returns zero only after filling the buffer.
 * A setup failure leaves out unchanged. On success, each record is usable only
 * when its respective status is VALID.
 *
 * Identity is missing when the fixed PLID frame is erased. Journal is missing
 * when both state sectors are completely erased. Journal core checks the full
 * erased padding of each decodable frame in 32-byte chunks. Checking for an
 * empty journal also scans padding, so inspection can read both entire sectors.
 */
enum rescue_inspection_result rescue_protected_inspect(
    const struct rescue_flash_geometry *geometry,
    const struct rescue_region *regions, size_t region_count,
    rescue_protected_read_fn read, void *context,
    const struct rescue_mac *inventory, size_t inventory_count,
    struct rescue_persistent_state *out);

#endif
