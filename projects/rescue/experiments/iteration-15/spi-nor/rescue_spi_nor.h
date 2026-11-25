#ifndef RESCUE_SPI_NOR_H
#define RESCUE_SPI_NOR_H

#include "../flash-probe/rescue_flash_probe.h"

enum rescue_spi_nor_result {
    RESCUE_SPI_NOR_OK = 0,
    RESCUE_SPI_NOR_INVALID,
    RESCUE_SPI_NOR_FAULTED,
    RESCUE_SPI_NOR_BUS_NOT_IDLE,
    RESCUE_SPI_NOR_TX_TIMEOUT,
    RESCUE_SPI_NOR_RX_TIMEOUT,
    RESCUE_SPI_NOR_WIP_TIMEOUT,
    RESCUE_SPI_NOR_WEL_ERROR,
    RESCUE_SPI_NOR_ID_ERROR
};

/* Caller-owned state. Zero-initialize before use and treat fields as read-only.
 * A trusted controller serializes calls and grants exclusive use of the
 * simulated bus. Each callback must return promptly. */
struct rescue_spi_nor {
    struct rescue_flash_bus bus;
    struct rescue_flash_geometry geometry;
    unsigned byte_budget;
    unsigned wip_budget;
    bool ready;
};

/* The caller must quiesce/reset the simulated bus before init, including
 * canceling any pending byte after a timeout. Init deasserts CS and checks
 * for TX readiness, empty RX and clear WIP/WEL before probing the ID.
 * byte_budget applies separately to each TX and RX readiness wait.
 * wip_budget limits the number of status transactions after a mutation. */
enum rescue_spi_nor_result rescue_spi_nor_init(
    struct rescue_spi_nor *nor, const struct rescue_flash_bus *bus,
    unsigned byte_budget, unsigned wip_budget);

/* All operations require successful init. Any rejected operation or transport
 * error disables commands until fresh init. A failed read can modify a prefix
 * of its output. A failed mutation may have changed flash. */
enum rescue_spi_nor_result rescue_spi_nor_read(
    struct rescue_spi_nor *nor, uint32_t address, void *data, size_t length);
enum rescue_spi_nor_result rescue_spi_nor_erase_sector(
    struct rescue_spi_nor *nor, uint32_t address);
/* Starts at a page boundary and writes between one byte and one full page. */
enum rescue_spi_nor_result rescue_spi_nor_program_page(
    struct rescue_spi_nor *nor, uint32_t address, const void *data, size_t length);

#endif
