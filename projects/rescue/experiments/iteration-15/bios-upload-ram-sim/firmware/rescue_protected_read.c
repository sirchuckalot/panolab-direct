#include "rescue_protected_read.h"

struct journal_reader {
    rescue_protected_read_fn read;
    void *context;
    struct rescue_region sectors[2];
    bool erased_frames[2];
};

static bool erased(const uint8_t *data, size_t length)
{
    for (size_t i = 0; i < length; ++i)
        if (data[i] != UINT8_MAX)
            return false;
    return true;
}

static int read_sector(void *context, unsigned sector, size_t offset,
                       uint8_t *data, size_t length)
{
    struct journal_reader *reader = context;
    if (sector >= 2)
        return -1;

    const struct rescue_region *region = &reader->sectors[sector];
    if (offset > region->length || length > region->length - offset)
        return -1;
    int result = reader->read(reader->context, region->offset + (uint32_t)offset,
                              data, length);
    if (result == 0 && offset == 0 && length == RESCUE_JOURNAL_RECORD_BYTES)
        reader->erased_frames[sector] = erased(data, length);
    return result;
}

static enum rescue_persistent_status inspect_journal(
    struct journal_reader *reader, struct rescue_journal_record *out)
{
    const struct rescue_journal_io io = {
        .context = reader,
        .sector_bytes = reader->sectors[0].length,
        .read = read_sector
    };

    switch (rescue_journal_read(&io, out)) {
    case RESCUE_JOURNAL_OK:
        return RESCUE_PERSISTENT_VALID;
    case RESCUE_JOURNAL_IO_ERROR:
        return RESCUE_PERSISTENT_READ_ERROR;
    case RESCUE_JOURNAL_NO_RECORD:
        break;
    default:
        return RESCUE_PERSISTENT_CORRUPT;
    }

    /* Journal core reports NO_RECORD for both erased and damaged sectors. */
    if (!reader->erased_frames[0] || !reader->erased_frames[1])
        return RESCUE_PERSISTENT_CORRUPT;

    uint8_t bytes[32];
    for (unsigned sector = 0; sector < 2; ++sector) {
        for (size_t offset = RESCUE_JOURNAL_RECORD_BYTES; offset < io.sector_bytes;) {
            size_t length = io.sector_bytes - offset;
            if (length > sizeof bytes)
                length = sizeof bytes;
            if (read_sector(reader, sector, offset, bytes, length))
                return RESCUE_PERSISTENT_READ_ERROR;
            if (!erased(bytes, length))
                return RESCUE_PERSISTENT_CORRUPT;
            offset += length;
        }
    }
    return RESCUE_PERSISTENT_MISSING;
}

enum rescue_inspection_result rescue_protected_inspect(
    const struct rescue_flash_geometry *geometry,
    const struct rescue_region *regions, size_t region_count,
    rescue_protected_read_fn read, void *context,
    const struct rescue_mac *inventory, size_t inventory_count,
    struct rescue_persistent_state *out)
{
    if (!regions || region_count == 0)
        return RESCUE_INSPECTION_NO_LAYOUT;
    if (!out || !read || (inventory_count && !inventory) ||
        !rescue_layout_valid(geometry, regions, region_count))
        return RESCUE_INSPECTION_INVALID;

    struct rescue_region identity = {0};
    struct journal_reader journal = {.read = read, .context = context};
    for (size_t i = 0; i < region_count; ++i) {
        switch (regions[i].role) {
        case RESCUE_REGION_IDENTITY:
            identity = regions[i];
            break;
        case RESCUE_REGION_STATE_0:
            journal.sectors[0] = regions[i];
            break;
        case RESCUE_REGION_STATE_1:
            journal.sectors[1] = regions[i];
            break;
        default:
            break;
        }
    }

    uint8_t frame[PANOLAB_IDENTITY_RECORD_BYTES];
    if (identity.length < sizeof frame ||
        journal.sectors[0].length < RESCUE_JOURNAL_RECORD_BYTES)
        return RESCUE_INSPECTION_INVALID;

    *out = (struct rescue_persistent_state){0};
    if (read(context, identity.offset, frame, sizeof frame))
        out->identity_status = RESCUE_PERSISTENT_READ_ERROR;
    else if (erased(frame, sizeof frame))
        out->identity_status = RESCUE_PERSISTENT_MISSING;
    else if (rescue_identity_decode(frame, sizeof frame, inventory,
                                    inventory_count, &out->identity))
        out->identity_status = RESCUE_PERSISTENT_VALID;
    else
        out->identity_status = RESCUE_PERSISTENT_CORRUPT;

    out->journal_status = inspect_journal(&journal, &out->journal);
    return RESCUE_INSPECTION_OK;
}
