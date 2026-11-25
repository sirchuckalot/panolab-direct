#include "rescue_storage.h"

/* LiteSPI a5a0090a: M25P128 and ST manufacturer ID. Erase size comes
 * from the proposed profile in PLR-ARCH-001 section 7.1. */
static const struct rescue_flash_geometry m25p128 = {
    0x7f1234u, 65536u, 4096u, 256u
};

bool rescue_geometry_lookup(uint32_t jedec_id,
                            struct rescue_flash_geometry *geometry)
{
    if (geometry == NULL || jedec_id != m25p128.jedec_id)
        return false;
    *geometry = m25p128;
    return true;
}

bool rescue_layout_valid(const struct rescue_flash_geometry *geometry,
                         const struct rescue_region *regions, size_t count)
{
    struct rescue_flash_geometry known;
    unsigned seen = 0;

    if (geometry == NULL || regions == NULL || count < 7 || count > 8 ||
        !rescue_geometry_lookup(geometry->jedec_id, &known) ||
        geometry->capacity != known.capacity ||
        geometry->erase_size != known.erase_size ||
        geometry->page_size != known.page_size)
        return false;

    for (size_t i = 0; i < count; ++i) {
        const struct rescue_region *region = &regions[i];
        unsigned role = (unsigned)region->role;

        if (role > RESCUE_REGION_RESERVED || (seen & (1u << role)) ||
            region->length == 0 || region->offset >= known.capacity ||
            region->length > known.capacity - region->offset ||
            region->offset % known.erase_size ||
            region->length % known.erase_size)
            return false;
        /* Erase alignment implies page alignment for this geometry. */
        if ((role == RESCUE_REGION_STATE_0 || role == RESCUE_REGION_STATE_1) &&
            region->length != known.erase_size)
            return false;

        for (size_t j = 0; j < i; ++j) {
            const struct rescue_region *other = &regions[j];
            if (region->offset < other->offset + other->length &&
                other->offset < region->offset + region->length)
                return false;
        }
        seen |= 1u << role;
    }
    return (seen & ((1u << RESCUE_REGION_RESERVED) - 1u)) ==
           ((1u << RESCUE_REGION_RESERVED) - 1u);
}

static bool is_app(enum rescue_slot slot)
{
    return slot == RESCUE_SLOT_A || slot == RESCUE_SLOT_B;
}

bool rescue_app_write_allowed(const struct rescue_flash_geometry *geometry,
                              const struct rescue_region *regions, size_t count,
                              const struct rescue_slot_protection *protection,
                              enum rescue_slot target, enum rescue_write_op op,
                              uint32_t offset, uint32_t length)
{
    if (protection == NULL || !protection->state_verified || !is_app(target) ||
        (protection->active != RESCUE_SLOT_NONE && !is_app(protection->active)) ||
        (protection->retained != RESCUE_SLOT_NONE && !is_app(protection->retained)) ||
        target == protection->active || target == protection->confirmed ||
        target == protection->retained ||
        (op != RESCUE_WRITE_ERASE && op != RESCUE_WRITE_PROGRAM) ||
        !rescue_layout_valid(geometry, regions, count))
        return false;

    if (protection->confirmed == RESCUE_SLOT_NONE) {
        if (protection->active != RESCUE_SLOT_NONE ||
            protection->retained != RESCUE_SLOT_NONE ||
            target != protection->selected_target)
            return false;
    } else if (!is_app(protection->confirmed)) {
        return false;
    }

    uint32_t alignment = op == RESCUE_WRITE_ERASE ?
                         geometry->erase_size : geometry->page_size;
    if (length == 0 || offset % alignment || length % alignment)
        return false;

    enum rescue_region_role role = target == RESCUE_SLOT_A ?
                                   RESCUE_REGION_APP_A : RESCUE_REGION_APP_B;
    for (size_t i = 0; i < count; ++i) {
        const struct rescue_region *region = &regions[i];
        if (region->role == role) {
            uint32_t end = region->offset + region->length;
            return offset >= region->offset && offset < end &&
                   length <= end - offset;
        }
    }
    return false;
}

static uint32_t crc_bytes(uint32_t crc, const void *data, size_t length)
{
    const unsigned char *bytes = data;
    for (size_t i = 0; i < length; ++i) {
        crc ^= bytes[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((crc & 1u) ? UINT32_C(0xedb88320) : 0u);
    }
    return crc;
}

uint32_t rescue_identity_crc(const struct rescue_identity *identity)
{
    if (identity == NULL)
        return 0;
    uint32_t crc = crc_bytes(UINT32_MAX, &identity->version, 1);
    crc = crc_bytes(crc, identity->device_id, sizeof identity->device_id);
    crc = crc_bytes(crc, identity->board_id, sizeof identity->board_id);
    crc = crc_bytes(crc, identity->board_revision, sizeof identity->board_revision);
    crc = crc_bytes(crc, identity->fpga_part, sizeof identity->fpga_part);
    crc = crc_bytes(crc, identity->mac.bytes, sizeof identity->mac.bytes);
    crc = crc_bytes(crc, identity->serial, sizeof identity->serial);
    crc = crc_bytes(crc, identity->source_provenance,
                    sizeof identity->source_provenance);
    return crc ^ UINT32_MAX;
}

static bool text_valid(const char *text, size_t length, bool optional)
{
    bool ended = false;
    if (!optional && text[0] == '\0')
        return false;
    for (size_t i = 0; i < length; ++i) {
        unsigned char byte = (unsigned char)text[i];
        if (byte == 0)
            ended = true;
        else if (ended || byte < 0x20 || byte > 0x7e)
            return false;
    }
    return ended;
}

static bool bytes_equal(const void *lhs, const void *rhs, size_t length)
{
    const unsigned char *a = lhs;
    const unsigned char *b = rhs;
    for (size_t i = 0; i < length; ++i)
        if (a[i] != b[i])
            return false;
    return true;
}

bool rescue_identity_valid(const struct rescue_identity *identity,
                           const struct rescue_mac *other_macs, size_t count)
{
    static const uint8_t zero_id[16] = {0};
    static const uint8_t erased_id[16] = {
        255, 255, 255, 255, 255, 255, 255, 255,
        255, 255, 255, 255, 255, 255, 255, 255
    };
    static const char board_id[sizeof identity->board_id] = "pano-g2";
    static const char board_revision[sizeof identity->board_revision] = "b";
    static const char fpga_part[sizeof identity->fpga_part] = "xc6slx150-2-fgg484";

    if (identity == NULL || (count != 0 && other_macs == NULL) ||
        identity->version != RESCUE_IDENTITY_VERSION ||
        bytes_equal(identity->device_id, zero_id, sizeof zero_id) ||
        bytes_equal(identity->device_id, erased_id, sizeof erased_id) ||
        !bytes_equal(identity->board_id, board_id, sizeof board_id) ||
        !bytes_equal(identity->board_revision, board_revision, sizeof board_revision) ||
        !bytes_equal(identity->fpga_part, fpga_part, sizeof fpga_part) ||
        !text_valid(identity->serial, sizeof identity->serial, true) ||
        !text_valid(identity->source_provenance, sizeof identity->source_provenance, false) ||
        (identity->mac.bytes[0] & 1u) ||
        bytes_equal(identity->mac.bytes, zero_id, sizeof identity->mac.bytes) ||
        identity->integrity_crc != rescue_identity_crc(identity))
        return false;

    for (size_t i = 0; i < count; ++i)
        if (bytes_equal(identity->mac.bytes, other_macs[i].bytes,
                        sizeof identity->mac.bytes))
            return false;
    return true;
}
