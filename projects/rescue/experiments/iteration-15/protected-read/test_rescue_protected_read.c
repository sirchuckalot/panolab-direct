#include "rescue_protected_read.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

enum { SECTOR = 262144, IDENTITY = 11 * SECTOR,
       STATE_0 = 14 * SECTOR, STATE_1 = 8 * SECTOR };

static const struct rescue_region layout[] = {
    {RESCUE_REGION_STATE_1, STATE_1, SECTOR},
    {RESCUE_REGION_BOOT, 0, SECTOR},
    {RESCUE_REGION_APP_B, 5 * SECTOR, SECTOR},
    {RESCUE_REGION_IDENTITY, IDENTITY, SECTOR},
    {RESCUE_REGION_STATE_0, STATE_0, SECTOR},
    {RESCUE_REGION_RESCUE, 2 * SECTOR, SECTOR},
    {RESCUE_REGION_APP_A, 3 * SECTOR, SECTOR}
};
#define REGION_COUNT (sizeof layout / sizeof layout[0])

static struct {
    uint8_t identity[PANOLAB_IDENTITY_RECORD_BYTES];
    uint8_t state[2][SECTOR];
    uint32_t fault_at;
    size_t calls;
    size_t bytes;
} flash;

static int read_flash(void *context, uint32_t address, uint8_t *data,
                      size_t length)
{
    assert(context == &flash);
    const uint8_t *source;
    if (address == IDENTITY && length == sizeof flash.identity) {
        source = flash.identity;
    } else if (address >= STATE_0 && address - STATE_0 < SECTOR) {
        assert(length <= SECTOR - (address - STATE_0));
        source = flash.state[0] + (address - STATE_0);
    } else {
        assert(address >= STATE_1 && address - STATE_1 < SECTOR);
        assert(length <= SECTOR - (address - STATE_1));
        source = flash.state[1] + (address - STATE_1);
    }

    ++flash.calls;
    flash.bytes += length;
    if (address <= flash.fault_at && flash.fault_at - address < length)
        return -1;
    memcpy(data, source, length);
    return 0;
}

static void load_identity(const char *board_id)
{
    struct rescue_identity identity = {
        .version = RESCUE_IDENTITY_VERSION,
        .device_id = {17},
        .board_revision = "b",
        .fpga_part = "xc6slx150-2-fgg484",
        .mac = {{2, 0, 0, 0, 0, 23}},
        .source_provenance = "synthetic fixture"
    };
    strcpy(identity.board_id, board_id);
    identity.integrity_crc = rescue_identity_crc(&identity);

    memcpy(flash.identity, "PLID", 4);
    size_t pos = 4;
#define PUT(field) do { \
    memcpy(flash.identity + pos, &identity.field, sizeof identity.field); \
    pos += sizeof identity.field; \
} while (0)
    PUT(version);
    PUT(device_id);
    PUT(board_id);
    PUT(board_revision);
    PUT(fpga_part);
    PUT(mac.bytes);
    PUT(serial);
    PUT(source_provenance);
#undef PUT
    for (unsigned i = 0; i < 4; ++i)
        flash.identity[pos++] = (uint8_t)(identity.integrity_crc >> (24 - 8 * i));
    assert(pos == sizeof flash.identity);
}

static void load_journal(unsigned sector, uint64_t sequence)
{
    const struct rescue_journal_record record = {
        .sequence = sequence,
        .confirmed = {.slot = RESCUE_JOURNAL_A, .digest = {0xab}},
        .state = RESCUE_RECORD_STABLE,
        .reason = "confirmed"
    };
    assert(rescue_journal_encode(&record, flash.state[sector]) ==
           RESCUE_JOURNAL_OK);
}

static struct rescue_flash_geometry geometry;

static struct rescue_persistent_state inspect(enum rescue_persistent_status id,
                                              enum rescue_persistent_status state)
{
    struct rescue_persistent_state result;
    assert(rescue_protected_inspect(&geometry, layout, REGION_COUNT, read_flash,
                                    &flash, NULL, 0, &result) ==
           RESCUE_INSPECTION_OK);
    assert(result.identity_status == id);
    assert(result.journal_status == state);
    return result;
}

int main(void)
{
    assert(rescue_geometry_lookup(0x202018, &geometry));
    struct rescue_persistent_state result = {.journal.sequence = 42};
    struct rescue_region bad_layout[REGION_COUNT];
    memcpy(bad_layout, layout, sizeof layout);
    bad_layout[0].offset = STATE_0;
    assert(rescue_protected_inspect(&geometry, bad_layout, REGION_COUNT,
                                    read_flash, &flash, NULL, 0, &result) ==
           RESCUE_INSPECTION_INVALID);
    assert(rescue_protected_inspect(&geometry, NULL, REGION_COUNT, read_flash,
                                    &flash, NULL, 0, &result) ==
           RESCUE_INSPECTION_NO_LAYOUT);
    assert(rescue_protected_inspect(&geometry, layout, 0, read_flash,
                                    &flash, NULL, 0, &result) ==
           RESCUE_INSPECTION_NO_LAYOUT);
    assert(flash.calls == 0 && result.journal.sequence == 42);

    memset(flash.identity, 0xff, sizeof flash.identity);
    memset(flash.state, 0xff, sizeof flash.state);
    flash.fault_at = UINT32_MAX;
    inspect(RESCUE_PERSISTENT_MISSING, RESCUE_PERSISTENT_MISSING);
    assert(flash.bytes == sizeof flash.identity + sizeof flash.state);
    flash.state[1][SECTOR - 1] = 0;
    inspect(RESCUE_PERSISTENT_MISSING, RESCUE_PERSISTENT_CORRUPT);
    flash.state[1][SECTOR - 1] = UINT8_MAX;

    load_identity("pano-g2");
    load_journal(0, 8);
    load_journal(1, 9);
    flash.bytes = 0;
    result = inspect(RESCUE_PERSISTENT_VALID, RESCUE_PERSISTENT_VALID);
    assert(result.identity.device_id[0] == 17 && result.journal.sequence == 9);
    assert(flash.bytes == sizeof flash.identity + sizeof flash.state);

    load_identity("wrong-board");
    inspect(RESCUE_PERSISTENT_CORRUPT, RESCUE_PERSISTENT_VALID);
    load_identity("pano-g2");

    flash.fault_at = IDENTITY;
    inspect(RESCUE_PERSISTENT_READ_ERROR, RESCUE_PERSISTENT_VALID);
    flash.fault_at = STATE_1;
    inspect(RESCUE_PERSISTENT_VALID, RESCUE_PERSISTENT_READ_ERROR);
    flash.fault_at = STATE_0 + SECTOR - 1;
    inspect(RESCUE_PERSISTENT_VALID, RESCUE_PERSISTENT_READ_ERROR);
    flash.fault_at = UINT32_MAX;

    load_journal(1, 10);
    inspect(RESCUE_PERSISTENT_VALID, RESCUE_PERSISTENT_CORRUPT);
    flash.state[1][SECTOR - 1] = 0;
    result = inspect(RESCUE_PERSISTENT_VALID, RESCUE_PERSISTENT_VALID);
    assert(result.journal.sequence == 8);
    flash.state[0][0] ^= 1;
    inspect(RESCUE_PERSISTENT_VALID, RESCUE_PERSISTENT_CORRUPT);

    puts("PASS: protected persistent state inspection");
    return 0;
}
