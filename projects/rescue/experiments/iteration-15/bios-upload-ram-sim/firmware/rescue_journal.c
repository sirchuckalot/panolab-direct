#include "rescue_journal.h"

enum {
    VERSION_OFFSET = 4,
    SEQUENCE_OFFSET = 5,
    CONFIRMED_OFFSET = 13,
    PENDING_OFFSET = 46,
    PREVIOUS_OFFSET = 79,
    STATE_OFFSET = 112,
    ATTEMPTS_OFFSET = 113,
    REASON_OFFSET = 114,
    CRC_OFFSET = 146,
    MARKER_OFFSET = 150
};

_Static_assert(MARKER_OFFSET + 1u == RESCUE_JOURNAL_RECORD_BYTES,
               "journal frame length");

static int equal(const uint8_t *a, const uint8_t *b, size_t size)
{
    for (size_t i = 0; i < size; ++i)
        if (a[i] != b[i])
            return 0;
    return 1;
}

static uint32_t crc32(const uint8_t *bytes, size_t size)
{
    uint32_t crc = UINT32_MAX;

    for (size_t i = 0; i < size; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xedb88320) : 0u);
    }
    return crc ^ UINT32_MAX;
}

static void put_binding(uint8_t *bytes, const struct rescue_journal_binding *binding)
{
    bytes[0] = binding->slot;
    for (size_t i = 0; i < RESCUE_JOURNAL_DIGEST_BYTES; ++i)
        bytes[i + 1] = binding->digest[i];
}

static void get_binding(struct rescue_journal_binding *binding, const uint8_t *bytes)
{
    binding->slot = bytes[0];
    for (size_t i = 0; i < RESCUE_JOURNAL_DIGEST_BYTES; ++i)
        binding->digest[i] = bytes[i + 1];
}

static int binding_valid(const struct rescue_journal_binding *binding)
{
    static const uint8_t zero[RESCUE_JOURNAL_DIGEST_BYTES] = {0};

    if (binding->slot == RESCUE_JOURNAL_NONE)
        return equal(binding->digest, zero, sizeof zero);
    return binding->slot == RESCUE_JOURNAL_A || binding->slot == RESCUE_JOURNAL_B;
}

static int same_slot(uint8_t a, uint8_t b)
{
    return a != RESCUE_JOURNAL_NONE && a == b;
}

enum rescue_journal_result rescue_journal_encode(
    const struct rescue_journal_record *record,
    uint8_t frame[RESCUE_JOURNAL_RECORD_BYTES])
{
    if (!record || !frame)
        return RESCUE_JOURNAL_INVALID;

    const uint8_t confirmed = record->confirmed.slot;
    const uint8_t pending = record->pending.slot;
    const uint8_t previous = record->previous.slot;
    const int trial_pending = record->state == RESCUE_RECORD_TRIAL_PENDING;
    const int trial = trial_pending || record->state == RESCUE_RECORD_TRIAL_RUNNING;

    if (!binding_valid(&record->confirmed) || !binding_valid(&record->pending) ||
        !binding_valid(&record->previous) ||
        same_slot(confirmed, pending) || same_slot(confirmed, previous) ||
        same_slot(pending, previous) || (previous && !confirmed) ||
        record->state < RESCUE_RECORD_STABLE ||
        record->state > RESCUE_RECORD_RECOVERY_ONLY ||
        trial != (pending != RESCUE_JOURNAL_NONE) ||
        record->attempts != trial_pending)
        return RESCUE_JOURNAL_INVALID;

    size_t reason_length = 0;
    while (reason_length < RESCUE_JOURNAL_REASON_BYTES &&
           record->reason[reason_length]) {
        const unsigned char c = (unsigned char)record->reason[reason_length];
        if ((c < 0x61 || c > 0x7a) && c != 0x5f)
            return RESCUE_JOURNAL_INVALID;
        ++reason_length;
    }
    if (!reason_length || record->reason[reason_length])
        return RESCUE_JOURNAL_INVALID;

    frame[0] = 0x52;
    frame[1] = 0x53;
    frame[2] = 0x4a;
    frame[3] = 0x31;
    frame[VERSION_OFFSET] = RESCUE_JOURNAL_VERSION;
    for (unsigned i = 0; i < 8; ++i)
        frame[SEQUENCE_OFFSET + i] = (uint8_t)(record->sequence >> (56u - 8u * i));
    put_binding(frame + CONFIRMED_OFFSET, &record->confirmed);
    put_binding(frame + PENDING_OFFSET, &record->pending);
    put_binding(frame + PREVIOUS_OFFSET, &record->previous);
    frame[STATE_OFFSET] = (uint8_t)(record->state - RESCUE_RECORD_STABLE);
    frame[ATTEMPTS_OFFSET] = record->attempts;
    for (size_t i = 0; i < RESCUE_JOURNAL_REASON_BYTES; ++i)
        frame[REASON_OFFSET + i] = i < reason_length ? (uint8_t)record->reason[i] : 0;

    const uint32_t crc = crc32(frame, CRC_OFFSET);
    for (unsigned i = 0; i < 4; ++i)
        frame[CRC_OFFSET + i] = (uint8_t)(crc >> (24u - 8u * i));
    frame[MARKER_OFFSET] = 0;
    return RESCUE_JOURNAL_OK;
}

static int decode(const uint8_t *frame, struct rescue_journal_record *record)
{
    uint8_t canonical[RESCUE_JOURNAL_RECORD_BYTES];

    if (frame[STATE_OFFSET] > RESCUE_RECORD_RECOVERY_ONLY - RESCUE_RECORD_STABLE)
        return 0;

    record->sequence = 0;
    for (unsigned i = 0; i < 8; ++i)
        record->sequence = (record->sequence << 8) | frame[SEQUENCE_OFFSET + i];
    get_binding(&record->confirmed, frame + CONFIRMED_OFFSET);
    get_binding(&record->pending, frame + PENDING_OFFSET);
    get_binding(&record->previous, frame + PREVIOUS_OFFSET);
    record->state = (uint8_t)(frame[STATE_OFFSET] + RESCUE_RECORD_STABLE);
    record->attempts = frame[ATTEMPTS_OFFSET];
    for (size_t i = 0; i < RESCUE_JOURNAL_REASON_BYTES; ++i)
        record->reason[i] = (char)frame[REASON_OFFSET + i];
    record->reason[RESCUE_JOURNAL_REASON_BYTES] = 0;

    return rescue_journal_encode(record, canonical) == RESCUE_JOURNAL_OK &&
           equal(frame, canonical, sizeof canonical);
}

static enum rescue_journal_result read_padding(
    const struct rescue_journal_io *io, unsigned sector)
{
    uint8_t bytes[32];
    size_t offset = RESCUE_JOURNAL_RECORD_BYTES;

    while (offset < io->sector_bytes) {
        size_t count = io->sector_bytes - offset;
        if (count > sizeof bytes)
            count = sizeof bytes;
        if (io->read(io->context, sector, offset, bytes, count))
            return RESCUE_JOURNAL_IO_ERROR;
        for (size_t i = 0; i < count; ++i)
            if (bytes[i] != UINT8_MAX)
                return RESCUE_JOURNAL_VERIFY_ERROR;
        offset += count;
    }
    return RESCUE_JOURNAL_OK;
}

static int readable(const struct rescue_journal_io *io)
{
    return io && io->read && io->sector_bytes >= RESCUE_JOURNAL_RECORD_BYTES;
}

static enum rescue_journal_result select_head(
    const struct rescue_journal_io *io, unsigned *active,
    uint8_t frames[2][RESCUE_JOURNAL_RECORD_BYTES],
    struct rescue_journal_record records[2])
{
    int valid[2];

    for (unsigned i = 0; i < 2; ++i) {
        if (io->read(io->context, i, 0, frames[i], RESCUE_JOURNAL_RECORD_BYTES))
            return RESCUE_JOURNAL_IO_ERROR;
        valid[i] = decode(frames[i], &records[i]);
        if (valid[i]) {
            const enum rescue_journal_result padding = read_padding(io, i);
            if (padding == RESCUE_JOURNAL_IO_ERROR)
                return padding;
            valid[i] = padding == RESCUE_JOURNAL_OK;
        }
    }
    if (!valid[0] && !valid[1])
        return RESCUE_JOURNAL_NO_RECORD;

    *active = !valid[0] || (valid[1] && records[1].sequence > records[0].sequence);
    if (valid[0] && valid[1] &&
        records[*active].sequence - records[1u - *active].sequence != 1)
        return RESCUE_JOURNAL_AMBIGUOUS;
    return RESCUE_JOURNAL_OK;
}

enum rescue_journal_result rescue_journal_read(
    const struct rescue_journal_io *io, struct rescue_journal_record *record)
{
    uint8_t frames[2][RESCUE_JOURNAL_RECORD_BYTES];
    struct rescue_journal_record records[2];
    unsigned active;

    if (!readable(io) || !record)
        return RESCUE_JOURNAL_INVALID;
    const enum rescue_journal_result result = select_head(io, &active, frames, records);
    if (result == RESCUE_JOURNAL_OK)
        *record = records[active];
    return result;
}

enum rescue_journal_result rescue_journal_commit(
    const struct rescue_journal_io *io,
    const struct rescue_journal_record *expected,
    const struct rescue_journal_record *next)
{
    uint8_t frames[2][RESCUE_JOURNAL_RECORD_BYTES];
    struct rescue_journal_record records[2];
    uint8_t frame[RESCUE_JOURNAL_RECORD_BYTES];
    unsigned active;

    if (!readable(io) || !io->erase || !io->program ||
        rescue_journal_encode(expected, frame) != RESCUE_JOURNAL_OK || !next)
        return RESCUE_JOURNAL_INVALID;

    enum rescue_journal_result result = select_head(io, &active, frames, records);
    if (result != RESCUE_JOURNAL_OK)
        return result;
    if (!equal(frame, frames[active], sizeof frame))
        return RESCUE_JOURNAL_STALE;
    if (records[active].sequence == UINT64_MAX)
        return RESCUE_JOURNAL_OVERFLOW;
    if (next->sequence != records[active].sequence + 1u ||
        rescue_journal_encode(next, frame) != RESCUE_JOURNAL_OK)
        return RESCUE_JOURNAL_INVALID;

    const unsigned target = 1u - active;
    if (io->erase(io->context, target) ||
        io->program(io->context, target, 0, frame, MARKER_OFFSET) ||
        io->read(io->context, target, 0, frames[target], sizeof frame))
        return RESCUE_JOURNAL_IO_ERROR;
    if (!equal(frame, frames[target], MARKER_OFFSET) ||
        frames[target][MARKER_OFFSET] != UINT8_MAX)
        return RESCUE_JOURNAL_VERIFY_ERROR;
    result = read_padding(io, target);
    if (result != RESCUE_JOURNAL_OK)
        return result;
    if (io->program(io->context, target, MARKER_OFFSET, frame + MARKER_OFFSET, 1))
        return RESCUE_JOURNAL_IO_ERROR;

    result = select_head(io, &active, frames, records);
    if (result == RESCUE_JOURNAL_IO_ERROR)
        return result;
    if (result != RESCUE_JOURNAL_OK || active != target ||
        !equal(frame, frames[target], sizeof frame))
        return RESCUE_JOURNAL_VERIFY_ERROR;
    return RESCUE_JOURNAL_OK;
}
