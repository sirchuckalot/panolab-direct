#include "rescue_storage.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define SECTOR UINT32_C(262144)
#define PAGE UINT32_C(256)
#define COUNT(array) (sizeof(array) / sizeof((array)[0]))

/* Synthetic layout with adjacent regions. */
static const struct rescue_region layout[] = {
    {RESCUE_REGION_BOOT, 0, SECTOR},
    {RESCUE_REGION_RESCUE, SECTOR, SECTOR},
    {RESCUE_REGION_APP_A, 2 * SECTOR, 2 * SECTOR},
    {RESCUE_REGION_APP_B, 4 * SECTOR, 2 * SECTOR},
    {RESCUE_REGION_IDENTITY, 6 * SECTOR, SECTOR},
    {RESCUE_REGION_STATE_0, 7 * SECTOR, SECTOR},
    {RESCUE_REGION_STATE_1, 8 * SECTOR, SECTOR},
    {RESCUE_REGION_RESERVED, 9 * SECTOR, 55 * SECTOR},
};

static struct rescue_flash_geometry geometry;

static void test_layout(void)
{
    assert(!rescue_geometry_lookup(0x202019u, &geometry));
    assert(!rescue_geometry_lookup(0xff202018u, &geometry));
    assert(!rescue_geometry_lookup(0x202018u, NULL));
    assert(rescue_geometry_lookup(0x202018u, &geometry));
    assert(geometry.jedec_id == 0x202018u);
    assert(geometry.capacity == 64 * SECTOR);
    assert(geometry.erase_size == SECTOR);
    assert(geometry.page_size == PAGE);
    assert(rescue_layout_valid(&geometry, layout, COUNT(layout)));
    assert(rescue_layout_valid(&geometry, layout, COUNT(layout) - 1));
    assert(!rescue_layout_valid(&geometry, layout, COUNT(layout) - 2));

    struct rescue_flash_geometry wrong = geometry;
    wrong.erase_size = 0;
    assert(!rescue_layout_valid(&wrong, layout, COUNT(layout)));

    const struct rescue_region invalid[] = {
        {RESCUE_REGION_APP_A, SECTOR, SECTOR},          /* Overlap. */
        {RESCUE_REGION_APP_A, 2 * SECTOR, UINT32_MAX - SECTOR + 1},
        {RESCUE_REGION_APP_A, UINT32_MAX - SECTOR + 1, SECTOR},
        {RESCUE_REGION_APP_A, 2 * SECTOR + PAGE, SECTOR},
        {RESCUE_REGION_APP_A, 2 * SECTOR, 0},
        {RESCUE_REGION_APP_B, 2 * SECTOR, 2 * SECTOR}, /* Duplicate role. */
        {(enum rescue_region_role)-1, 2 * SECTOR, SECTOR},
    };
    struct rescue_region changed[COUNT(layout)];
    memcpy(changed, layout, sizeof changed);
    for (size_t i = 0; i < COUNT(invalid); ++i) {
        changed[2] = invalid[i];
        assert(!rescue_layout_valid(&geometry, changed, COUNT(changed)));
    }

    memcpy(changed, layout, sizeof changed);
    changed[5].offset = 10 * SECTOR;
    changed[5].length = 2 * SECTOR;
    assert(!rescue_layout_valid(&geometry, changed, COUNT(changed) - 1));
}

static bool allowed(const struct rescue_slot_protection *protection,
                    enum rescue_slot target, enum rescue_write_op op,
                    uint32_t offset, uint32_t length)
{
    return rescue_app_write_allowed(&geometry, layout, COUNT(layout),
                                    protection, target, op, offset, length);
}

static void test_protection(void)
{
    const struct rescue_slot_protection normal = {
        .confirmed = RESCUE_SLOT_A,
        .state_verified = true,
    };
    assert(allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_ERASE, 4 * SECTOR, SECTOR));
    assert(allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_PROGRAM, 6 * SECTOR - PAGE, PAGE));
    assert(!allowed(&normal, RESCUE_SLOT_A, RESCUE_WRITE_ERASE, 2 * SECTOR, SECTOR));
    assert(!allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_PROGRAM, 6 * SECTOR - PAGE, 2 * PAGE));
    assert(!allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_PROGRAM, 4 * SECTOR, UINT32_MAX - PAGE + 1));
    assert(!allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_PROGRAM, 4 * SECTOR, 0));
    assert(!allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_PROGRAM, 4 * SECTOR + 1, PAGE));
    assert(!allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_ERASE, 4 * SECTOR, PAGE));
    assert(!allowed(&normal, RESCUE_SLOT_B, (enum rescue_write_op)2, 4 * SECTOR, PAGE));
    assert(!allowed(&normal, RESCUE_SLOT_NONE, RESCUE_WRITE_ERASE, 4 * SECTOR, SECTOR));

    for (size_t i = 0; i < COUNT(layout); ++i) {
        if (layout[i].role != RESCUE_REGION_APP_B)
            assert(!allowed(&normal, RESCUE_SLOT_B, RESCUE_WRITE_ERASE,
                            layout[i].offset, SECTOR));
    }

    const struct rescue_slot_protection denied[] = {
        {0},
        {.confirmed = RESCUE_SLOT_A},
        {.confirmed = RESCUE_SLOT_A, .active = RESCUE_SLOT_B, .state_verified = true},
        {.confirmed = RESCUE_SLOT_A, .retained = RESCUE_SLOT_B, .state_verified = true},
        {.confirmed = (enum rescue_slot)3, .state_verified = true},
        {.confirmed = RESCUE_SLOT_A, .active = (enum rescue_slot)3, .state_verified = true},
        {.confirmed = RESCUE_SLOT_A, .retained = (enum rescue_slot)3, .state_verified = true},
        {.selected_target = RESCUE_SLOT_B},
        {.state_verified = true},
        {.state_verified = true, .selected_target = (enum rescue_slot)3},
        {.active = RESCUE_SLOT_A, .state_verified = true, .selected_target = RESCUE_SLOT_B},
        {.retained = RESCUE_SLOT_A, .state_verified = true, .selected_target = RESCUE_SLOT_B},
    };
    for (size_t i = 0; i < COUNT(denied); ++i)
        assert(!allowed(&denied[i], RESCUE_SLOT_B, RESCUE_WRITE_ERASE, 4 * SECTOR, SECTOR));
    assert(!allowed(NULL, RESCUE_SLOT_B, RESCUE_WRITE_ERASE, 4 * SECTOR, SECTOR));

    struct rescue_slot_protection first = {
        .state_verified = true,
        .selected_target = RESCUE_SLOT_B,
    };
    assert(allowed(&first, RESCUE_SLOT_B, RESCUE_WRITE_ERASE, 4 * SECTOR, SECTOR));
    assert(allowed(&first, RESCUE_SLOT_B, RESCUE_WRITE_PROGRAM, 4 * SECTOR, PAGE));
    assert(!allowed(&first, RESCUE_SLOT_A, RESCUE_WRITE_ERASE, 2 * SECTOR, SECTOR));
    first.selected_target = RESCUE_SLOT_A;
    assert(allowed(&first, RESCUE_SLOT_A, RESCUE_WRITE_ERASE, 2 * SECTOR, SECTOR));
    assert(!allowed(&first, RESCUE_SLOT_B, RESCUE_WRITE_ERASE, 4 * SECTOR, SECTOR));
}

static void test_identity(void)
{
    /* Synthetic test fixture. CRC independently computed over 183 bytes. */
    const struct rescue_identity fixture = {
        .version = 1,
        .device_id = {1},
        .board_id = "pano-g2",
        .board_revision = "b",
        .fpga_part = "xc6slx150-2-fgg484",
        .mac = {{2, 0, 0, 0, 0, 1}},
        .source_provenance = "test fixture",
        .integrity_crc = UINT32_C(0xa0972a6a),
    };
    const struct rescue_mac inventory[] = {
        {{2, 0, 0, 0, 0, 2}},
        {{2, 0, 0, 0, 0, 1}},
    };
    assert(rescue_identity_crc(&fixture) == fixture.integrity_crc);
    assert(rescue_identity_valid(&fixture, NULL, 0));
    assert(rescue_identity_valid(&fixture, inventory, 1));
    assert(!rescue_identity_valid(&fixture, inventory, COUNT(inventory)));
    assert(!rescue_identity_valid(&fixture, NULL, 1));

    struct rescue_identity changed = fixture;
    changed.device_id[1] ^= 1;
    assert(!rescue_identity_valid(&changed, NULL, 0));

    struct rescue_identity invalid[] = {fixture, fixture, fixture, fixture, fixture};
    invalid[0].board_id[6] = '1';
    invalid[1].board_revision[0] = 'B';
    invalid[2].fpga_part[10] = '3';
    invalid[3].board_id[sizeof invalid[3].board_id - 1] = 'x';
    invalid[4].mac.bytes[0] = 3;
    for (size_t i = 0; i < COUNT(invalid); ++i) {
        invalid[i].integrity_crc = rescue_identity_crc(&invalid[i]);
        assert(!rescue_identity_valid(&invalid[i], NULL, 0));
    }
}

int main(void)
{
    test_layout();
    test_protection();
    test_identity();
    puts("storage-core tests passed");
    return 0;
}
