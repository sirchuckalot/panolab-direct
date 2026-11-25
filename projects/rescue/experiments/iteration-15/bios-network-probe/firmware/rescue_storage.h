#ifndef RESCUE_STORAGE_H
#define RESCUE_STORAGE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

struct rescue_flash_geometry {
    uint32_t jedec_id; /* Manufacturer, type, density in bits 23:0. */
    uint32_t capacity;
    uint32_t erase_size;
    uint32_t page_size;
};

bool rescue_geometry_lookup(uint32_t jedec_id,
                            struct rescue_flash_geometry *geometry);

enum rescue_region_role {
    RESCUE_REGION_BOOT = 0,
    RESCUE_REGION_RESCUE,
    RESCUE_REGION_APP_A,
    RESCUE_REGION_APP_B,
    RESCUE_REGION_IDENTITY,
    RESCUE_REGION_STATE_0,
    RESCUE_REGION_STATE_1,
    RESCUE_REGION_RESERVED
};

struct rescue_region {
    enum rescue_region_role role;
    uint32_t offset;
    uint32_t length;
};

bool rescue_layout_valid(const struct rescue_flash_geometry *geometry,
                         const struct rescue_region *regions, size_t count);

enum rescue_slot { RESCUE_SLOT_NONE = 0, RESCUE_SLOT_A, RESCUE_SLOT_B };

struct rescue_slot_protection {
    enum rescue_slot active;    /* NONE while running Rescue. */
    enum rescue_slot confirmed; /* NONE before the first confirmation. */
    enum rescue_slot retained;  /* NONE when no separate rollback is retained. */
    bool state_verified; /* Set only after validating an initialized journal. */
    enum rescue_slot selected_target; /* First staging slot selected by the caller. */
};

enum rescue_write_op { RESCUE_WRITE_ERASE = 0, RESCUE_WRITE_PROGRAM };

/*
 * Authorize one absolute byte range inside the named app slot. Program spans
 * cover whole pages; the caller splits the span into individual page commands.
 * Hold layout and verified protection state stable through flash execution.
 */
bool rescue_app_write_allowed(const struct rescue_flash_geometry *geometry,
                              const struct rescue_region *regions, size_t count,
                              const struct rescue_slot_protection *protection,
                              enum rescue_slot target, enum rescue_write_op op,
                              uint32_t offset, uint32_t length);

#define RESCUE_IDENTITY_VERSION 1u

struct rescue_mac {
    uint8_t bytes[6];
};

/*
 * Normalized Ethernet identity. Required text fields are nonempty printable
 * ASCII, NUL-terminated and zero-padded. Serial may be empty. device_id is an
 * opaque 16-byte stable identifier. Struct layout is an in-memory API.
 */
struct rescue_identity {
    uint8_t version;
    uint8_t device_id[16];
    char board_id[24];
    char board_revision[8];
    char fpga_part[32];
    struct rescue_mac mac;
    char serial[32];
    char source_provenance[64];
    uint32_t integrity_crc;
};

/* CRC-32/ISO-HDLC over the fields in declaration order before integrity_crc,
 * including all text padding, excluding any compiler-inserted padding. */
uint32_t rescue_identity_crc(const struct rescue_identity *identity);

/* Requires the exact Pano G2 board, revision and FPGA part. Inventory contains
 * known MACs for other devices. An empty inventory skips the duplicate check.
 * The caller supplies provisioning evidence. */
bool rescue_identity_valid(const struct rescue_identity *identity,
                           const struct rescue_mac *other_macs, size_t count);

#endif
