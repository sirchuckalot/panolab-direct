#include "op_ledger.h"

/*
 * v1 frame: "OLED", version, state, three uint64 counters (generation,
 * epoch, operation ID), uint64 journal sequence, 32 digest bytes, CRC-32,
 * commit marker. All integers are little endian. CRC covers the 70 bytes preceding the CRC.
 */
enum { CRC_OFFSET = OL_BODY_SIZE - 4u };

static bool equal(const uint8_t *a, const uint8_t *b, unsigned length)
{
    for (unsigned i = 0; i < length; ++i)
        if (a[i] != b[i])
            return false;
    return true;
}

static void put_le(uint8_t *bytes, uint64_t value, unsigned length)
{
    for (unsigned i = 0; i < length; ++i) {
        bytes[i] = (uint8_t)value;
        value >>= 8;
    }
}

static uint64_t get_le(const uint8_t *bytes, unsigned length)
{
    uint64_t value = 0;
    while (length != 0)
        value = (value << 8) | bytes[--length];
    return value;
}

static uint32_t crc32(const uint8_t *bytes, unsigned length)
{
    uint32_t crc = UINT32_MAX;
    for (unsigned i = 0; i < length; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xedb88320) : 0u);
    }
    return ~crc;
}

static const uint8_t magic[] = {0x4f, 0x4c, 0x45, 0x44, 1};

static void encode(const ol_record *r, uint8_t frame[OL_FRAME_SIZE])
{
    for (unsigned i = 0; i < sizeof magic; ++i)
        frame[i] = magic[i];
    frame[5] = (uint8_t)r->state;
    put_le(frame + 6, r->generation, 8);
    put_le(frame + 14, r->boot_epoch, 8);
    put_le(frame + 22, r->operation_id, 8);
    put_le(frame + 30, r->journal_sequence, 8);
    for (unsigned i = 0; i < OL_DIGEST_SIZE; ++i)
        frame[38 + i] = r->digest[i];
    put_le(frame + CRC_OFFSET, crc32(frame, CRC_OFFSET), 4);
    frame[OL_BODY_SIZE] = OL_UNCOMMITTED_MARKER;
}

static bool decode(const uint8_t frame[OL_FRAME_SIZE], ol_record *r)
{
    static const uint8_t zero[OL_DIGEST_SIZE] = {0};
    if (!equal(frame, magic, sizeof magic) || frame[5] > OL_INTERRUPTED ||
        get_le(frame + CRC_OFFSET, 4) != crc32(frame, CRC_OFFSET))
        return false;
    r->state = (ol_state)frame[5];
    r->generation = get_le(frame + 6, 8);
    r->boot_epoch = get_le(frame + 14, 8);
    r->operation_id = get_le(frame + 22, 8);
    r->journal_sequence = get_le(frame + 30, 8);
    for (unsigned i = 0; i < OL_DIGEST_SIZE; ++i)
        r->digest[i] = frame[38 + i];

    if (r->generation == 0 || r->boot_epoch >= r->generation ||
        r->operation_id >= r->generation - r->boot_epoch)
        return false;
    if (r->state == OL_NONE)
        return r->operation_id == 0 && r->journal_sequence == 0 &&
               equal(r->digest, zero, OL_DIGEST_SIZE) &&
               r->boot_epoch == r->generation - 1;
    return r->operation_id != 0 && r->boot_epoch != 0;
}

static bool terminal_state(ol_state state)
{
    return state == OL_SEALED || state == OL_CANCELLED;
}

static bool follows(const ol_record *old, const ol_record *next)
{
    bool same_operation = next->operation_id == old->operation_id &&
                          equal(next->digest, old->digest, OL_DIGEST_SIZE);
    if (next->generation <= old->generation ||
        next->generation - old->generation != 1)
        return false;
    if (next->boot_epoch > old->boot_epoch)
        return next->boot_epoch - old->boot_epoch == 1 && same_operation &&
               next->journal_sequence == old->journal_sequence &&
               next->state == (old->state == OL_RESERVED ? OL_INTERRUPTED : old->state);
    if (next->boot_epoch != old->boot_epoch)
        return false;
    if (old->state == OL_RESERVED)
        return same_operation && next->journal_sequence == old->journal_sequence && terminal_state(next->state);
    return next->state == OL_RESERVED && next->operation_id > old->operation_id &&
           next->operation_id - old->operation_id == 1;
}

static ol_result scan(ol_ledger *ledger, bool provision)
{
    ol_record records[2];
    bool valid[2] = {false, false};
    bool empty = true;
    bool io = false;
    bool corrupt = false;
    for (unsigned i = 0; i < 2; ++i) {
        uint8_t frame[OL_FRAME_SIZE];
        const ol_store *store = &ledger->stores[i];
        switch (store->read(store->context, frame)) {
        case OL_READ_EMPTY:
            break;
        case OL_READ_FRAME:
            empty = false;
            if (frame[OL_BODY_SIZE] == OL_COMMITTED_MARKER) {
                valid[i] = decode(frame, &records[i]);
                corrupt |= !valid[i];
            } else if (frame[OL_BODY_SIZE] != OL_UNCOMMITTED_MARKER) {
                corrupt = true;
            }
            break;
        default:
            io = true;
            break;
        }
    }
    if (io)
        return OL_IO;
    if (corrupt)
        return OL_CORRUPT;
    if (provision)
        return empty ? OL_OK : OL_NOT_EMPTY;
    if (!valid[0] && !valid[1])
        return empty ? OL_UNPROVISIONED : OL_CORRUPT;
    unsigned active = !valid[0] ||
                      (valid[1] && records[1].generation > records[0].generation);
    if (valid[0] && valid[1] && !follows(&records[1u - active], &records[active]))
        return OL_CORRUPT;
    ledger->active = active;
    ledger->current = records[active];
    return OL_OK;
}

static ol_result persist(ol_ledger *ledger, unsigned target, const ol_record *next)
{
    uint8_t expected[OL_FRAME_SIZE], observed[OL_FRAME_SIZE];
    const ol_store *store = &ledger->stores[target];
    ledger->ready = false;
    encode(next, expected);
    if (!store->erase(store->context) ||
        !store->write_body(store->context, expected) ||
        store->read(store->context, observed) != OL_READ_FRAME ||
        !equal(expected, observed, OL_FRAME_SIZE) ||
        !store->commit(store->context, OL_COMMITTED_MARKER))
        return OL_IO;

    expected[OL_BODY_SIZE] = OL_COMMITTED_MARKER;
    if (store->read(store->context, observed) != OL_READ_FRAME ||
        !equal(expected, observed, OL_FRAME_SIZE))
        return OL_IO;

    ledger->active = target;
    ledger->current = *next;
    return OL_OK;
}

ol_result ol_init(ol_ledger *ledger, ol_store first, ol_store second)
{
    if (!ledger)
        return OL_ARGUMENT;
    ledger->ready = false;
    ledger->initialized = false;
    if (!first.read || !first.erase || !first.write_body || !first.commit ||
        !second.read || !second.erase || !second.write_body || !second.commit)
        return OL_ARGUMENT;
    ledger->stores[0] = first;
    ledger->stores[1] = second;
    ledger->initialized = true;
    return OL_OK;
}

ol_result ol_provision(ol_ledger *ledger)
{
    if (!ledger)
        return OL_ARGUMENT;
    if (!ledger->initialized || ledger->ready)
        return OL_STATE;
    ol_result result = scan(ledger, true);
    if (result != OL_OK)
        return result;
    const ol_record initial = {.generation = 1};
    return persist(ledger, 0, &initial);
}

ol_result ol_boot(ol_ledger *ledger)
{
    if (!ledger)
        return OL_ARGUMENT;
    if (!ledger->initialized)
        return OL_STATE;
    ledger->ready = false;
    ol_result result = scan(ledger, false);
    if (result != OL_OK)
        return result;
    ol_record next = ledger->current;
    if (next.generation == UINT64_MAX || next.boot_epoch == UINT64_MAX)
        return OL_OVERFLOW;
    ++next.generation;
    ++next.boot_epoch;
    if (next.state == OL_RESERVED)
        next.state = OL_INTERRUPTED;
    result = persist(ledger, 1u - ledger->active, &next);
    ledger->ready = result == OL_OK;
    return result;
}

ol_result ol_snapshot(const ol_ledger *ledger, ol_record *record)
{
    if (!ledger || !record)
        return OL_ARGUMENT;
    if (!ledger->ready)
        return OL_STATE;
    *record = ledger->current;
    return OL_OK;
}

ol_result ol_reserve(ol_ledger *ledger, const uint8_t digest[OL_DIGEST_SIZE],
                     uint64_t journal_sequence, uint64_t *operation_id)
{
    if (!ledger || !digest || !operation_id)
        return OL_ARGUMENT;
    if (!ledger->ready || ledger->current.state == OL_RESERVED)
        return OL_STATE;
    ol_record next = ledger->current;
    if (next.generation == UINT64_MAX || next.operation_id == UINT64_MAX) {
        ledger->ready = false;
        return OL_OVERFLOW;
    }
    ++next.generation;
    ++next.operation_id;
    next.state = OL_RESERVED;
    next.journal_sequence = journal_sequence;
    for (unsigned i = 0; i < OL_DIGEST_SIZE; ++i)
        next.digest[i] = digest[i];
    ol_result result = persist(ledger, 1u - ledger->active, &next);
    ledger->ready = result == OL_OK;
    if (ledger->ready)
        *operation_id = next.operation_id;
    return result;
}

ol_result ol_finish(ol_ledger *ledger, uint64_t operation_id,
                    const uint8_t digest[OL_DIGEST_SIZE],
                    uint64_t journal_sequence, ol_state terminal)
{
    if (!ledger || !digest || !terminal_state(terminal))
        return OL_ARGUMENT;
    if (!ledger->ready || ledger->current.state != OL_RESERVED)
        return OL_STATE;
    ol_record next = ledger->current;
    if (next.operation_id != operation_id || next.journal_sequence != journal_sequence || !equal(next.digest, digest, OL_DIGEST_SIZE))
        return OL_MISMATCH;
    if (next.generation == UINT64_MAX) {
        ledger->ready = false;
        return OL_OVERFLOW;
    }
    ++next.generation;
    next.state = terminal;
    next.journal_sequence = journal_sequence;
    ol_result result = persist(ledger, 1u - ledger->active, &next);
    ledger->ready = result == OL_OK;
    return result;
}
