#include "rescue_spi_nor.h"

enum {
    CMD_READ = 0x03, CMD_RDSR = 0x05, CMD_WREN = 0x06,
    CMD_ERASE = 0xd8, CMD_PROGRAM = 0x02,
    SR_WIP = 0x01, SR_WEL = 0x02
};

static bool wait_ready(bool (*ready)(void *), void *context, unsigned budget)
{
    for (; budget != 0; --budget) {
        if (ready(context))
            return true;
    }
    return false;
}

static enum rescue_spi_nor_result exchange(const struct rescue_spi_nor *nor,
                                           uint8_t tx, uint8_t *rx)
{
    const struct rescue_flash_bus *bus = &nor->bus;

    if (!wait_ready(bus->tx_ready, bus->context, nor->byte_budget))
        return RESCUE_SPI_NOR_TX_TIMEOUT;
    bus->tx_byte(bus->context, tx);
    if (!wait_ready(bus->rx_ready, bus->context, nor->byte_budget))
        return RESCUE_SPI_NOR_RX_TIMEOUT;
    uint8_t byte = bus->rx_byte(bus->context);
    if (rx != NULL)
        *rx = byte;
    return RESCUE_SPI_NOR_OK;
}

static enum rescue_spi_nor_result command(
    const struct rescue_spi_nor *nor, uint8_t opcode, bool addressed,
    uint32_t address, const uint8_t *tx, uint8_t *rx, size_t length)
{
    const struct rescue_flash_bus *bus = &nor->bus;
    void *context = bus->context;

    if (bus->rx_ready(context))
        return RESCUE_SPI_NOR_BUS_NOT_IDLE;

    bus->select(context, true);
    enum rescue_spi_nor_result result = exchange(nor, opcode, NULL);
    for (int shift = 16; addressed && shift >= 0 && !result; shift -= 8)
        result = exchange(nor, (uint8_t)(address >> shift), NULL);
    for (size_t i = 0; i < length && !result; ++i)
        result = exchange(nor, tx ? tx[i] : 0, rx ? &rx[i] : NULL);
    bus->select(context, false);
    return result;
}

static enum rescue_spi_nor_result status(const struct rescue_spi_nor *nor,
                                         uint8_t *value)
{
    return command(nor, CMD_RDSR, false, 0, NULL, value, 1);
}

enum rescue_spi_nor_result rescue_spi_nor_init(
    struct rescue_spi_nor *nor, const struct rescue_flash_bus *bus,
    unsigned byte_budget, unsigned wip_budget)
{
    if (nor == NULL)
        return RESCUE_SPI_NOR_INVALID;
    nor->ready = false;
    nor->geometry = (struct rescue_flash_geometry){0};
    if (bus == NULL || !bus->select || !bus->tx_ready || !bus->rx_ready ||
        !bus->tx_byte || !bus->rx_byte || !byte_budget || !wip_budget)
        return RESCUE_SPI_NOR_INVALID;

    nor->bus = *bus;
    nor->byte_budget = byte_budget;
    nor->wip_budget = wip_budget;
    bus->select(bus->context, false);
    if (!wait_ready(bus->tx_ready, bus->context, byte_budget))
        return RESCUE_SPI_NOR_TX_TIMEOUT;
    uint8_t value;
    enum rescue_spi_nor_result result = status(nor, &value);
    if (result)
        return result;
    if (value & (SR_WIP | SR_WEL))
        return RESCUE_SPI_NOR_BUS_NOT_IDLE;

    switch (rescue_flash_probe(bus, byte_budget, &nor->geometry)) {
    case RESCUE_FLASH_PROBE_OK:
        break;
    case RESCUE_FLASH_PROBE_TX_TIMEOUT:
        return RESCUE_SPI_NOR_TX_TIMEOUT;
    case RESCUE_FLASH_PROBE_RX_TIMEOUT:
        return RESCUE_SPI_NOR_RX_TIMEOUT;
    case RESCUE_FLASH_PROBE_STALE_RX:
        return RESCUE_SPI_NOR_BUS_NOT_IDLE;
    default:
        return RESCUE_SPI_NOR_ID_ERROR;
    }
    nor->ready = true;
    return RESCUE_SPI_NOR_OK;
}

static enum rescue_spi_nor_result finish(struct rescue_spi_nor *nor,
                                         enum rescue_spi_nor_result result)
{
    if (result)
        nor->ready = false;
    return result;
}

static bool valid_range(const struct rescue_spi_nor *nor, uint32_t address,
                        size_t length)
{
    return length != 0 && address < nor->geometry.capacity &&
           length <= nor->geometry.capacity - address;
}

enum rescue_spi_nor_result rescue_spi_nor_read(
    struct rescue_spi_nor *nor, uint32_t address, void *data, size_t length)
{
    if (nor == NULL || !nor->ready)
        return RESCUE_SPI_NOR_FAULTED;
    if (data == NULL || !valid_range(nor, address, length))
        return finish(nor, RESCUE_SPI_NOR_INVALID);
    return finish(nor, command(nor, CMD_READ, true, address, NULL, data, length));
}
