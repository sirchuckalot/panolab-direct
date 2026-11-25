#include "rescue_flash_transaction.h"

struct journal_reader {
    const struct rescue_flash_io *io;
    uint32_t offsets[2];
};

static int read_journal(void *context, unsigned sector, size_t offset,
                        uint8_t *data, size_t length)
{
    const struct journal_reader *reader = context;
    return reader->io->read(reader->io->context,
                            reader->offsets[sector] + (uint32_t)offset,
                            data, length);
}

struct flash_image_reader {
    const struct rescue_flash_io *io;
    uint32_t base;
};

static size_t read_flash_image(void *context, uint64_t offset,
                               uint8_t *data, size_t length)
{
    const struct flash_image_reader *reader = context;
    return reader->io->read(reader->io->context, reader->base + (uint32_t)offset,
                            data, length) == 0 ? length : 0;
}

static enum rescue_slot app_slot(uint8_t slot)
{
    if (slot == RESCUE_JOURNAL_A)
        return RESCUE_SLOT_A;
    if (slot == RESCUE_JOURNAL_B)
        return RESCUE_SLOT_B;
    return RESCUE_SLOT_NONE;
}

static uint32_t round_up(uint32_t length, uint32_t alignment)
{
    return ((length - 1u) / alignment + 1u) * alignment;
}

enum rescue_flash_result rescue_flash_stage(
    const struct rescue_flash_io *io,
    const struct rescue_flash_stage_request *request,
    struct rescue_flash_verified *verified)
{
    uint8_t page[256];
    uint8_t expected_frame[RESCUE_JOURNAL_RECORD_BYTES];
    uint8_t current_frame[RESCUE_JOURNAL_RECORD_BYTES];
    struct rescue_journal_record current;

    if (!io || !io->read || !io->erase || !io->program || !request ||
        !verified || !request->metadata || !request->policy ||
        !request->read_image ||
        (request->target != RESCUE_SLOT_A && request->target != RESCUE_SLOT_B))
        return RESCUE_FLASH_ARGUMENT;

    const struct rescue_flash_geometry *geometry = request->geometry;
    if (!rescue_layout_valid(geometry, request->regions, request->region_count) ||
        geometry->page_size > sizeof page)
        return RESCUE_FLASH_LAYOUT;

    struct journal_reader journal_reader = { .io = io };
    const struct rescue_region *target = NULL;
    const enum rescue_region_role target_role = request->target == RESCUE_SLOT_A ?
                                               RESCUE_REGION_APP_A : RESCUE_REGION_APP_B;
    for (size_t i = 0; i < request->region_count; ++i) {
        const struct rescue_region *region = &request->regions[i];
        if (region->role == target_role)
            target = region;
        else if (region->role == RESCUE_REGION_STATE_0)
            journal_reader.offsets[0] = region->offset;
        else if (region->role == RESCUE_REGION_STATE_1)
            journal_reader.offsets[1] = region->offset;
    }

    if (rescue_journal_encode(request->expected, expected_frame) != RESCUE_JOURNAL_OK)
        return RESCUE_FLASH_JOURNAL;
    if (request->metadata->role != PL_APPLICATION || !target ||
        request->raw_length == 0 || request->raw_length > target->length ||
        pl_image_verify(request->metadata, request->policy, request->raw_length,
                        request->read_image, request->image_context) != PL_IMAGE_OK)
        return RESCUE_FLASH_IMAGE;

    const struct rescue_journal_io journal = {
        .context = &journal_reader, .sector_bytes = geometry->erase_size,
        .read = read_journal
    };
    enum rescue_journal_result journal_result = rescue_journal_read(&journal, &current);
    if (journal_result == RESCUE_JOURNAL_IO_ERROR)
        return RESCUE_FLASH_IO;
    if (journal_result != RESCUE_JOURNAL_OK ||
        rescue_journal_encode(&current, current_frame) != RESCUE_JOURNAL_OK ||
        current.pending.slot != RESCUE_JOURNAL_NONE)
        return RESCUE_FLASH_JOURNAL;

    for (size_t i = 0; i < sizeof current_frame; ++i)
        if (expected_frame[i] != current_frame[i])
            return RESCUE_FLASH_STALE;

    const struct rescue_slot_protection protection = {
        .active = request->active, .confirmed = app_slot(current.confirmed.slot),
        .retained = app_slot(current.previous.slot), .state_verified = true,
        .selected_target = request->target
    };
    const uint32_t length = (uint32_t)request->raw_length;
    const uint32_t erase_span = round_up(length, geometry->erase_size);
    const uint32_t program_span = round_up(length, geometry->page_size);
    if (!rescue_app_write_allowed(geometry, request->regions, request->region_count,
                                  &protection, request->target, RESCUE_WRITE_ERASE,
                                  target->offset, erase_span) ||
        !rescue_app_write_allowed(geometry, request->regions, request->region_count,
                                  &protection, request->target, RESCUE_WRITE_PROGRAM,
                                  target->offset, program_span))
        return RESCUE_FLASH_PROTECTED;

    for (uint32_t offset = 0; offset < erase_span; offset += geometry->erase_size)
        if (io->erase(io->context, target->offset + offset))
            return RESCUE_FLASH_IO;

    for (uint32_t offset = 0; offset < program_span; offset += geometry->page_size) {
        size_t count = length - offset;
        if (count > geometry->page_size)
            count = geometry->page_size;
        if (request->read_image(request->image_context, offset, page, count) != count)
            return RESCUE_FLASH_IMAGE;
        for (size_t i = count; i < geometry->page_size; ++i)
            page[i] = 0xff;
        if (io->program(io->context, target->offset + offset, page, geometry->page_size))
            return RESCUE_FLASH_IO;
    }

    struct flash_image_reader reader = { .io = io, .base = target->offset };
    if (pl_image_verify(request->metadata, request->policy, length,
                        read_flash_image, &reader) != PL_IMAGE_OK)
        return RESCUE_FLASH_READBACK;

    verified->slot = request->target;
    verified->image_length = length;
    for (size_t i = 0; i < sizeof verified->digest; ++i)
        verified->digest[i] = request->metadata->image_sha256[i];
    return RESCUE_FLASH_OK;
}
