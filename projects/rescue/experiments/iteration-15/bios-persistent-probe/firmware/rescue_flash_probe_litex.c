#include "rescue_flash_probe.h"
#include "rescue_spi_nor.h"

#include <generated/csr.h>

/* LiteX liblitespi spiflash.c (afed6623) uses these master fields for
 * byte transfers: eight bits, one lane, drive mask 1, and CS bit 0. */
static void litex_select(void *context, bool selected)
{
    (void)context;
    if (selected) {
        spiflash_master_phyconfig_write(
            (8u << CSR_SPIFLASH_MASTER_PHYCONFIG_LEN_OFFSET) |
            (1u << CSR_SPIFLASH_MASTER_PHYCONFIG_WIDTH_OFFSET) |
            (1u << CSR_SPIFLASH_MASTER_PHYCONFIG_MASK_OFFSET));
    }
    spiflash_master_cs_write(selected ? 1u : 0u);
}

static bool litex_tx_ready(void *context)
{
    (void)context;
    return (spiflash_master_status_read() &
            (1u << CSR_SPIFLASH_MASTER_STATUS_TX_READY_OFFSET)) != 0;
}

static bool litex_rx_ready(void *context)
{
    (void)context;
    return (spiflash_master_status_read() &
            (1u << CSR_SPIFLASH_MASTER_STATUS_RX_READY_OFFSET)) != 0;
}

static void litex_tx_byte(void *context, uint8_t byte)
{
    (void)context;
    spiflash_master_rxtx_write(byte);
}

static uint8_t litex_rx_byte(void *context)
{
    (void)context;
    return (uint8_t)spiflash_master_rxtx_read();
}

static const struct rescue_flash_bus bus = {
        .select = litex_select, .tx_ready = litex_tx_ready, .rx_ready = litex_rx_ready,
        .tx_byte = litex_tx_byte, .rx_byte = litex_rx_byte,
};

enum rescue_spi_nor_result rescue_nor_litex_init(struct rescue_spi_nor *nor)
{
    return rescue_spi_nor_init(nor, &bus, 50000u, 1u);
}

enum rescue_flash_probe_result rescue_flash_probe_litex(
    unsigned budget, struct rescue_flash_geometry *geometry)
{
    return rescue_flash_probe(&bus, budget, geometry);
}
