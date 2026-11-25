#include "rescue_flash_probe.h"

#include <assert.h>
#include <stdio.h>

#define BUDGET 3u

struct fake_bus {
    uint32_t ids[2];
    unsigned transactions;
    unsigned closes;
    unsigned sent;
    unsigned tx_polls;
    unsigned rx_polls;
    unsigned stale;
    unsigned discarded;
    unsigned stall_tx_at;
    unsigned stall_rx_at;
    bool selected;
    bool pending;
};

static void select_flash(void *context, bool selected)
{
    struct fake_bus *fake = context;
    if (selected) {
        assert(!fake->selected && !fake->pending && !fake->stale);
        assert(fake->transactions < 2);
        assert(fake->sent == 4 * fake->transactions);
        ++fake->transactions;
    } else if (fake->selected) {
        ++fake->closes;
        fake->pending = false;
    }
    fake->selected = selected;
}

static bool tx_ready(void *context)
{
    struct fake_bus *fake = context;
    assert(fake->selected && !fake->pending);
    ++fake->tx_polls;
    return fake->sent + 1 != fake->stall_tx_at;
}

static bool rx_ready(void *context)
{
    struct fake_bus *fake = context;
    ++fake->rx_polls;
    if (!fake->selected)
        return fake->stale != 0;
    assert(fake->pending);
    return fake->sent != fake->stall_rx_at;
}

static void tx_byte(void *context, uint8_t byte)
{
    struct fake_bus *fake = context;
    assert(fake->selected && !fake->pending && fake->sent < 8);
    assert(byte == (fake->sent % 4 == 0 ? 0x9f : 0x00));
    ++fake->sent;
    fake->pending = true;
}

static uint8_t rx_byte(void *context)
{
    struct fake_bus *fake = context;
    if (!fake->selected) {
        assert(fake->stale > 0);
        --fake->stale;
        ++fake->discarded;
        return 0xff;
    }

    assert(fake->pending);
    fake->pending = false;
    unsigned index = (fake->sent - 1) % 4;
    if (index == 0)
        return (uint8_t)(0xa0u + fake->transactions);
    return (uint8_t)(fake->ids[fake->transactions - 1] >> (8 * (3 - index)));
}

static struct rescue_flash_bus bind_bus(struct fake_bus *fake)
{
    return (struct rescue_flash_bus){
        .context = fake,
        .select = select_flash,
        .tx_ready = tx_ready,
        .rx_ready = rx_ready,
        .tx_byte = tx_byte,
        .rx_byte = rx_byte,
    };
}

static void assert_cleared(struct rescue_flash_geometry geometry)
{
    assert(geometry.jedec_id == 0 && geometry.capacity == 0 &&
           geometry.erase_size == 0 && geometry.page_size == 0);
}

static void check_probe(struct fake_bus *fake, enum rescue_flash_probe_result expected,
                        unsigned sent, unsigned transactions)
{
    struct rescue_flash_bus bus = bind_bus(fake);
    struct rescue_flash_geometry geometry = {1, 2, 3, 4};
    assert(rescue_flash_probe(&bus, BUDGET, &geometry) == expected);
    assert(!fake->selected && fake->sent == sent);
    assert(fake->transactions == transactions && fake->closes == transactions);
    if (expected == RESCUE_FLASH_PROBE_OK) {
        struct rescue_flash_geometry known;
        assert(rescue_geometry_lookup(0x202018, &known));
        assert(geometry.jedec_id == known.jedec_id &&
               geometry.capacity == known.capacity &&
               geometry.erase_size == known.erase_size &&
               geometry.page_size == known.page_size);
    } else {
        assert_cleared(geometry);
    }
}

int main(void)
{
    struct fake_bus valid = {.ids = {0x202018, 0x202018}, .stale = BUDGET};
    check_probe(&valid, RESCUE_FLASH_PROBE_OK, 8, 2);
    assert(valid.discarded == BUDGET);

    struct fake_bus mismatch = {.ids = {0x202018, 0x202019}};
    check_probe(&mismatch, RESCUE_FLASH_PROBE_DISAGREEMENT, 8, 2);
    struct fake_bus unknown = {.ids = {0x202019, 0x202019}};
    check_probe(&unknown, RESCUE_FLASH_PROBE_UNKNOWN_ID, 8, 2);
    struct fake_bus floating = {.ids = {0xffffff, 0xffffff}};
    check_probe(&floating, RESCUE_FLASH_PROBE_UNKNOWN_ID, 8, 2);
    struct fake_bus zero = {0};
    check_probe(&zero, RESCUE_FLASH_PROBE_UNKNOWN_ID, 8, 2);

    struct fake_bus stale = {.stale = BUDGET + 1};
    check_probe(&stale, RESCUE_FLASH_PROBE_STALE_RX, 0, 0);
    assert(stale.discarded == BUDGET && stale.rx_polls == BUDGET + 1);

    for (unsigned byte = 1; byte <= 8; ++byte) {
        unsigned transactions = byte <= 4 ? 1 : 2;
        struct fake_bus tx_stall = {.stall_tx_at = byte};
        check_probe(&tx_stall, RESCUE_FLASH_PROBE_TX_TIMEOUT, byte - 1, transactions);
        assert(tx_stall.tx_polls == byte - 1 + BUDGET);
        struct fake_bus rx_stall = {.stall_rx_at = byte};
        check_probe(&rx_stall, RESCUE_FLASH_PROBE_RX_TIMEOUT, byte, transactions);
        assert(rx_stall.rx_polls == byte - 1 + BUDGET + transactions);
    }

    struct fake_bus invalid = {.selected = true};
    struct rescue_flash_bus bus = bind_bus(&invalid);
    struct rescue_flash_geometry geometry = {1, 2, 3, 4};
    assert(rescue_flash_probe(&bus, 0, &geometry) == RESCUE_FLASH_PROBE_INVALID);
    assert(!invalid.selected && invalid.sent == 0 && invalid.closes == 1);
    assert_cleared(geometry);
    assert(rescue_flash_probe(&bus, BUDGET, NULL) == RESCUE_FLASH_PROBE_INVALID);
    assert(rescue_flash_probe(NULL, BUDGET, &geometry) == RESCUE_FLASH_PROBE_INVALID);
    bus.rx_byte = NULL;
    assert(rescue_flash_probe(&bus, BUDGET, &geometry) == RESCUE_FLASH_PROBE_INVALID);
    assert(invalid.transactions == 0 && invalid.sent == 0);

    puts("SPI JEDEC probe tests passed");
    return 0;
}
