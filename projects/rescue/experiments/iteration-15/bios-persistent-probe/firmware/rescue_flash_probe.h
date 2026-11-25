#ifndef RESCUE_FLASH_PROBE_H
#define RESCUE_FLASH_PROBE_H

#include "rescue_storage.h"

/* Operations must return promptly. Selecting CS also prepares 8-bit,
 * single-lane transfers. Each TX byte must produce one RX byte. */
struct rescue_flash_bus {
    void *context;
    void (*select)(void *context, bool selected);
    bool (*tx_ready)(void *context);
    bool (*rx_ready)(void *context);
    void (*tx_byte)(void *context, uint8_t byte);
    uint8_t (*rx_byte)(void *context);
};

enum rescue_flash_probe_result {
    RESCUE_FLASH_PROBE_OK = 0,
    RESCUE_FLASH_PROBE_INVALID,
    RESCUE_FLASH_PROBE_STALE_RX,
    RESCUE_FLASH_PROBE_TX_TIMEOUT,
    RESCUE_FLASH_PROBE_RX_TIMEOUT,
    RESCUE_FLASH_PROBE_DISAGREEMENT,
    RESCUE_FLASH_PROBE_UNKNOWN_ID
};

/* Caller owns an idle bus exclusively. budget limits readiness checks per
 * byte and stale bytes discarded per transaction. Geometry is cleared on
 * failure when supplied. */
enum rescue_flash_probe_result rescue_flash_probe(
    const struct rescue_flash_bus *bus, unsigned budget,
    struct rescue_flash_geometry *geometry);

/* LiteX binding. Requires the generated LiteSPI master CSR accessors. */
enum rescue_flash_probe_result rescue_flash_probe_litex(
    unsigned budget, struct rescue_flash_geometry *geometry);

#endif
