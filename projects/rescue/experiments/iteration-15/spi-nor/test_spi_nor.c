#include "rescue_spi_nor.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CAPACITY = 0x1000000, SECTOR = 0x40000, PAGE = 256,
    BYTE_BUDGET = 3, WIP_BUDGET = 4, BASE = 0x140000,
    WIP = 1, WEL = 2
};

struct frame {
    size_t length;
    uint8_t bytes[4 + PAGE];
};

struct fake {
    const struct frame *frames;
    size_t frame_count, next_frame, position;
    uint32_t address, id;
    unsigned tx_waits, rx_waits, busy;
    unsigned tx_checks, rx_checks, cs_calls;
    uint8_t response;
    bool selected, pending, stale_rx;
    bool wel, ignore_wren, retain_wel, stuck_busy;
    bool stall_tx, stall_rx;
};

static uint8_t memory[CAPACITY];

static void select_bus(void *context, bool selected)
{
    struct fake *f = context;
    ++f->cs_calls;
    if (selected) {
        assert(!f->selected && !f->pending);
        assert(f->next_frame < f->frame_count);
        f->position = 0;
        f->address = 0;
    } else if (f->selected) {
        const struct frame *frame = &f->frames[f->next_frame++];
        assert(f->position == frame->length);
        assert(!f->pending || f->stall_rx);

        if (frame->length && frame->bytes[0] == 0x06)
            f->wel = !f->ignore_wren;
        if (frame->length >= 4 &&
            (frame->bytes[0] == 0xd8 || frame->bytes[0] == 0x02)) {
            assert(f->wel && !f->busy);
            assert(f->address < CAPACITY);
            if (frame->bytes[0] == 0xd8) {
                assert(f->address % SECTOR == 0);
                memset(memory + f->address, 0xff, SECTOR);
            } else {
                for (size_t i = 4; i < frame->length; ++i)
                    memory[f->address + i - 4] &= frame->bytes[i];
            }
            f->wel = f->retain_wel;
            f->busy = 2;
        }
    }
    f->selected = selected;
}

static bool tx_ready(void *context)
{
    struct fake *f = context;
    ++f->tx_checks;
    if (f->selected && f->stall_tx &&
        f->position == f->frames[f->next_frame].length) {
        assert(++f->tx_waits <= BYTE_BUDGET);
        return false;
    }
    return true;
}

static bool rx_ready(void *context)
{
    struct fake *f = context;
    ++f->rx_checks;
    if (f->pending && f->stall_rx) {
        assert(++f->rx_waits <= BYTE_BUDGET);
        return false;
    }
    return f->pending || f->stale_rx;
}

static void tx_byte(void *context, uint8_t byte)
{
    struct fake *f = context;
    assert(f->selected && !f->pending);
    const struct frame *frame = &f->frames[f->next_frame];
    size_t i = f->position++;
    assert(i < frame->length && byte == frame->bytes[i]);
    f->pending = true;
    f->response = 0;

    uint8_t opcode = frame->bytes[0];
    if (i && opcode == 0x9f) {
        f->response = (uint8_t)(f->id >> (8 * (3 - i)));
    } else if (i && opcode == 0x05) {
        f->response = (f->wel ? WEL : 0) |
                      (f->busy ? WIP : 0);
        if (f->busy && !f->stuck_busy)
            --f->busy;
    } else if (i && (opcode == 0x03 || opcode == 0x02 || opcode == 0xd8)) {
        if (i < 4)
            f->address = (f->address << 8) | byte;
        else if (opcode == 0x03)
            f->response = memory[f->address + i - 4];
    }
}

static uint8_t rx_byte(void *context)
{
    struct fake *f = context;
    assert(f->selected && f->pending);
    f->pending = false;
    return f->response;
}

#define SCRIPT(f, ...) \
    expect((f), (const struct frame[]){__VA_ARGS__}, \
           sizeof((const struct frame[]){__VA_ARGS__}) / sizeof(struct frame))
#define STATUS {2, {0x05, 0}}
#define ID {4, {0x9f, 0, 0, 0}}
#define WREN {1, {0x06}}
#define PROGRAM {7, {0x02, 0x14, 0x23, 0, 0xa5, 0x5a, 0x0f}}
#define ERASE {4, {0xd8, 0x14, 0, 0}}

static void expect(struct fake *f, const struct frame *frames, size_t count)
{
    assert(!f->selected && f->next_frame == f->frame_count);
    f->frames = frames;
    f->frame_count = count;
    f->next_frame = 0;
}

static void frames_done(const struct fake *f)
{
    assert(!f->selected && f->next_frame == f->frame_count);
}

static enum rescue_spi_nor_result init(struct rescue_spi_nor *nor, struct fake *f)
{
    const struct rescue_flash_bus bus = {
        f, select_bus, tx_ready, rx_ready, tx_byte, rx_byte
    };
    return rescue_spi_nor_init(nor, &bus, BYTE_BUDGET, WIP_BUDGET);
}

static void init_ok(struct rescue_spi_nor *nor, struct fake *f)
{
    f->id = 0x202018;
    SCRIPT(f, STATUS, ID, ID);
    assert(init(nor, f) == RESCUE_SPI_NOR_OK);
    frames_done(f);
    assert(nor->geometry.jedec_id == f->id);
    assert(nor->geometry.capacity == CAPACITY);
    assert(nor->geometry.page_size == PAGE);
    assert(nor->geometry.erase_size == SECTOR);
}

static void faulted(struct rescue_spi_nor *nor, const struct fake *f)
{
    uint8_t byte = 0;
    unsigned cs = f->cs_calls, tx = f->tx_checks, rx = f->rx_checks;
    frames_done(f);
    assert(rescue_spi_nor_read(nor, 0, &byte, 1) == RESCUE_SPI_NOR_FAULTED);
    assert(rescue_spi_nor_program_page(nor, 0, &byte, 1) == RESCUE_SPI_NOR_FAULTED);
    assert(rescue_spi_nor_erase_sector(nor, 0) == RESCUE_SPI_NOR_FAULTED);
    assert(cs == f->cs_calls && tx == f->tx_checks && rx == f->rx_checks);
}

static void test_memory(void)
{
    struct fake f = {0};
    struct rescue_spi_nor nor = {0};
    static const uint8_t data[] = {0xa5, 0x5a, 0x0f};
    uint8_t out[4];

    init_ok(&nor, &f);
    memset(memory + BASE, 0xff, SECTOR);
    memory[BASE + 0x2300] = 0xf0;
    memory[BASE - 1] = 0x12;
    memory[BASE + SECTOR] = 0x34;
    SCRIPT(&f, WREN, STATUS, PROGRAM, STATUS, STATUS, STATUS);
    assert(rescue_spi_nor_program_page(&nor, BASE + 0x2300, data, sizeof(data))
           == RESCUE_SPI_NOR_OK);

    SCRIPT(&f, {8, {0x03, 0x14, 0x23, 0x00, 0, 0, 0, 0}});
    assert(rescue_spi_nor_read(&nor, BASE + 0x2300, out, sizeof(out))
           == RESCUE_SPI_NOR_OK);
    assert(memcmp(out, (const uint8_t[]){0xa0, 0x5a, 0x0f, 0xff}, sizeof(out)) == 0);

    SCRIPT(&f, WREN, STATUS, ERASE, STATUS, STATUS, STATUS);
    assert(rescue_spi_nor_erase_sector(&nor, BASE) == RESCUE_SPI_NOR_OK);
    frames_done(&f);
    for (size_t i = 0; i < SECTOR; ++i)
        assert(memory[BASE + i] == 0xff);
    assert(memory[BASE - 1] == 0x12 && memory[BASE + SECTOR] == 0x34);

    memory[CAPACITY - 1] = 0x81;
    SCRIPT(&f, {5, {0x03, 0xff, 0xff, 0xff, 0}});
    assert(rescue_spi_nor_read(&nor, CAPACITY - 1, out, 1) == RESCUE_SPI_NOR_OK);
    assert(out[0] == 0x81);
    frames_done(&f);
}

static void test_invalid(void)
{
    struct fake f = {0};
    struct rescue_spi_nor nor = {0};
    uint8_t data[PAGE + 1] = {0};

#define REJECT(operation) do { \
    init_ok(&nor, &f); \
    assert((operation) == RESCUE_SPI_NOR_INVALID); \
    faulted(&nor, &f); \
} while (0)
    REJECT(rescue_spi_nor_read(&nor, CAPACITY - 1, data, 2));
    REJECT(rescue_spi_nor_read(&nor, CAPACITY, data, 1));
    REJECT(rescue_spi_nor_read(&nor, UINT32_MAX, data, SIZE_MAX));
    REJECT(rescue_spi_nor_read(&nor, 1, data, 0));
    REJECT(rescue_spi_nor_program_page(&nor, BASE + 1, data, 1));
    REJECT(rescue_spi_nor_program_page(&nor, BASE, data, sizeof(data)));
    REJECT(rescue_spi_nor_program_page(&nor, CAPACITY, data, 1));
    REJECT(rescue_spi_nor_erase_sector(&nor, BASE + PAGE));
    REJECT(rescue_spi_nor_erase_sector(&nor, CAPACITY));
#undef REJECT
}

static void test_init_failures(void)
{
    struct fake f = {.id = 0x202019};
    struct rescue_spi_nor nor = {0};

    SCRIPT(&f, STATUS, ID, ID);
    assert(init(&nor, &f) == RESCUE_SPI_NOR_ID_ERROR);
    faulted(&nor, &f);

    SCRIPT(&f, STATUS);
    f.wel = true;
    assert(init(&nor, &f) == RESCUE_SPI_NOR_BUS_NOT_IDLE);
    faulted(&nor, &f);
    f.wel = false;

    f.stale_rx = true;
    assert(init(&nor, &f) == RESCUE_SPI_NOR_BUS_NOT_IDLE);
    faulted(&nor, &f);
    f.stale_rx = false;
    init_ok(&nor, &f);
}

static void test_transport_failures(void)
{
    struct fake f = {0};
    struct rescue_spi_nor nor = {0};
    uint8_t out = 0x77;

    init_ok(&nor, &f);
    SCRIPT(&f, {2, {0x03, 0x14}});
    f.stall_tx = true;
    assert(rescue_spi_nor_read(&nor, BASE, &out, 1) == RESCUE_SPI_NOR_TX_TIMEOUT);
    assert(f.tx_waits == BYTE_BUDGET && out == 0x77);
    faulted(&nor, &f);

    f.stall_tx = false;
    init_ok(&nor, &f);
    SCRIPT(&f, {1, {0x06}});
    f.stall_rx = true;
    assert(rescue_spi_nor_erase_sector(&nor, BASE) == RESCUE_SPI_NOR_RX_TIMEOUT);
    assert(f.rx_waits == BYTE_BUDGET && f.pending);
    faulted(&nor, &f);

    f.stall_rx = false;
    f.pending = false;
    f.wel = false;
    init_ok(&nor, &f);
}

static void test_status_failures(void)
{
    struct fake f = {0};
    struct rescue_spi_nor nor = {0};

    init_ok(&nor, &f);
    f.ignore_wren = true;
    SCRIPT(&f, WREN, STATUS);
    assert(rescue_spi_nor_erase_sector(&nor, BASE) == RESCUE_SPI_NOR_WEL_ERROR);
    faulted(&nor, &f);

    f.ignore_wren = false;
    init_ok(&nor, &f);
    f.retain_wel = true;
    SCRIPT(&f, WREN, STATUS, ERASE, STATUS, STATUS, STATUS);
    assert(rescue_spi_nor_erase_sector(&nor, BASE) == RESCUE_SPI_NOR_WEL_ERROR);
    faulted(&nor, &f);

    f.retain_wel = false;
    f.wel = false;
    init_ok(&nor, &f);
    /* Keep WIP asserted for every poll after the erase. */
    SCRIPT(&f, WREN, STATUS, ERASE, STATUS, STATUS, STATUS, STATUS);
    f.stuck_busy = true;
    assert(rescue_spi_nor_erase_sector(&nor, BASE) == RESCUE_SPI_NOR_WIP_TIMEOUT);
    faulted(&nor, &f);
}

int main(void)
{
    test_memory();
    test_invalid();
    test_init_failures();
    test_transport_failures();
    test_status_failures();
    puts("SPI NOR tests passed");
    return 0;
}
