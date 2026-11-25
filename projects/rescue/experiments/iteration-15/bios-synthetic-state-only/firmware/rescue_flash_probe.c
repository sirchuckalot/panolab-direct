#include "rescue_flash_probe.h"

static bool wait_ready(bool (*ready)(void *), void *context, unsigned budget)
{
    for (unsigned i = 0; i < budget; ++i) {
        if (ready(context))
            return true;
    }
    return false;
}

static enum rescue_flash_probe_result read_id(
    const struct rescue_flash_bus *bus, unsigned budget, uint32_t *id)
{
    static const uint8_t request[] = {0x9f, 0x00, 0x00, 0x00};
    void *context = bus->context;
    enum rescue_flash_probe_result result = RESCUE_FLASH_PROBE_OK;

    for (unsigned drained = 0; bus->rx_ready(context); ++drained) {
        if (drained == budget)
            return RESCUE_FLASH_PROBE_STALE_RX;
        (void)bus->rx_byte(context);
    }

    *id = 0;
    bus->select(context, true);
    for (size_t i = 0; i < sizeof(request); ++i) {
        if (!wait_ready(bus->tx_ready, context, budget)) {
            result = RESCUE_FLASH_PROBE_TX_TIMEOUT;
            break;
        }
        bus->tx_byte(context, request[i]);
        if (!wait_ready(bus->rx_ready, context, budget)) {
            result = RESCUE_FLASH_PROBE_RX_TIMEOUT;
            break;
        }
        uint8_t byte = bus->rx_byte(context);
        if (i != 0)
            *id = (*id << 8) | byte;
    }
    bus->select(context, false);
    return result;
}

enum rescue_flash_probe_result rescue_flash_probe(
    const struct rescue_flash_bus *bus, unsigned budget,
    struct rescue_flash_geometry *geometry)
{
    uint32_t first, second;
    enum rescue_flash_probe_result result;

    if (bus != NULL && bus->select != NULL)
        bus->select(bus->context, false);
    if (geometry != NULL)
        *geometry = (struct rescue_flash_geometry){0};
    if (geometry == NULL || budget == 0 || bus == NULL ||
        bus->select == NULL || bus->tx_ready == NULL ||
        bus->rx_ready == NULL || bus->tx_byte == NULL || bus->rx_byte == NULL)
        return RESCUE_FLASH_PROBE_INVALID;

    result = read_id(bus, budget, &first);
    if (result != RESCUE_FLASH_PROBE_OK)
        return result;
    result = read_id(bus, budget, &second);
    if (result != RESCUE_FLASH_PROBE_OK)
        return result;
    if (first != second)
        return RESCUE_FLASH_PROBE_DISAGREEMENT;
    if (!rescue_geometry_lookup(first, geometry))
        return RESCUE_FLASH_PROBE_UNKNOWN_ID;
    return RESCUE_FLASH_PROBE_OK;
}
