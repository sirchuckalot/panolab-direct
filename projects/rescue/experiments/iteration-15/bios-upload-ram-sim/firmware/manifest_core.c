/* PanoLab Trusted-LAN manifest parser. SPDX-License-Identifier: GPL-3.0-or-later */
#include "manifest_core.h"

struct cursor {
    const uint8_t *next;
    size_t remaining;
};

static const uint8_t *take(struct cursor *c, size_t count)
{
    const uint8_t *start = c->next;
    if (count > c->remaining)
        return NULL;
    c->next += count;
    c->remaining -= count;
    return start;
}

/* Decode a definite-length header and enforce preferred serialization. */
static int head(struct cursor *c, unsigned major, uint64_t *value)
{
    const uint8_t *first = take(c, 1);
    if (first == NULL || (unsigned)(*first >> 5) != major)
        return 0;
    unsigned info = *first & 31u;
    if (info < 24u) {
        *value = info;
        return 1;
    }
    if (info > 27u)
        return 0;
    size_t count = (size_t)1u << (info - 24u);
    const uint8_t *data = take(c, count);
    if (data == NULL)
        return 0;
    uint64_t n = 0;
    for (size_t i = 0; i < count; ++i)
        n = (n << 8) | data[i];
    static const uint64_t minima[] = {24, 256, 65536, UINT64_C(4294967296)};
    *value = n;
    return n >= minima[info - 24u];
}

static int exact(struct cursor *c, unsigned major, uint64_t expected)
{
    uint64_t value;
    return head(c, major, &value) && value == expected;
}

static int literal(struct cursor *c, const char *expected, size_t length)
{
    if (!exact(c, 3, length))
        return 0;
    const uint8_t *data = take(c, length);
    if (data == NULL)
        return 0;
    for (size_t i = 0; i < length; ++i)
        if (data[i] != (uint8_t)expected[i])
            return 0;
    return 1;
}

#define TEXT(c, s) literal((c), (s), sizeof(s) - 1u)

static int printable(struct cursor *c)
{
    uint64_t length;
    if (!head(c, 3, &length) || length == 0 || length > PL_MANIFEST_MAX_TEXT)
        return 0;
    const uint8_t *data = take(c, (size_t)length);
    if (data == NULL)
        return 0;
    for (size_t i = 0; i < (size_t)length; ++i)
        if (data[i] < 0x20u || data[i] > 0x7eu)
            return 0;
    return 1;
}

static int target(struct cursor *c)
{
    return exact(c, 4, 1) && exact(c, 5, 4)
        && TEXT(c, "board_id") && TEXT(c, "pano-g2")
        && TEXT(c, "fpga_part") && TEXT(c, "xc6slx150-2-fgg484")
        && TEXT(c, "bsp_profile") && TEXT(c, "pano-g2-revb/1")
        && TEXT(c, "board_revision") && TEXT(c, "b");
}

static int provenance(struct cursor *c)
{
    uint64_t fields, count;
    if (!head(c, 5, &fields) || (fields != 3 && fields != 4))
        return 0;
    if (fields == 4 && !(TEXT(c, "build_id") && printable(c)))
        return 0;
    if (!(TEXT(c, "toolchain") && printable(c)
          && TEXT(c, "git_commit") && exact(c, 3, 40)))
        return 0;
    const uint8_t *commit = take(c, 40);
    if (commit == NULL)
        return 0;
    for (size_t i = 0; i < 40; ++i)
        if (!(commit[i] >= '0' && commit[i] <= '9')
            && !(commit[i] >= 'a' && commit[i] <= 'f'))
            return 0;
    if (!(TEXT(c, "dependency_pins") && head(c, 4, &count))
        || count > PL_MANIFEST_MAX_PINS)
        return 0;
    for (size_t i = 0; i < (size_t)count; ++i)
        if (!printable(c))
            return 0;
    return 1;
}

enum pl_manifest_result pl_manifest_parse(const uint8_t *bytes, size_t length,
                                          struct pl_manifest *output)
{
    if (bytes == NULL || output == NULL)
        return PL_MANIFEST_ARGUMENT;
    if (length == 0 || length > PL_MANIFEST_MAX_SIZE)
        return PL_MANIFEST_SIZE;

    struct cursor c = {bytes, length};
    uint64_t image_length, feature_count, api_minor;
    if (!(exact(&c, 5, 11)
          && TEXT(&c, "image_id") && printable(&c)
          && TEXT(&c, "image_role") && TEXT(&c, "application")
          && TEXT(&c, "image_length") && head(&c, 0, &image_length)
          && image_length != 0
          && TEXT(&c, "image_sha256") && exact(&c, 2, PL_SHA256_SIZE)))
        return PL_MANIFEST_INVALID;
    const uint8_t *image_digest = take(&c, PL_SHA256_SIZE);
    if (image_digest == NULL
        || !(TEXT(&c, "config_format") && TEXT(&c, "xilinx-spartan6-spi")
             && TEXT(&c, "image_version") && printable(&c)
             && TEXT(&c, "build_provenance") && provenance(&c)
             && TEXT(&c, "manifest_version") && exact(&c, 0, 1)
             && TEXT(&c, "required_features") && head(&c, 4, &feature_count)
             && feature_count <= 1))
        return PL_MANIFEST_INVALID;
    if (feature_count == 1 && !TEXT(&c, "icap-return-v1"))
        return PL_MANIFEST_INVALID;
    if (!(TEXT(&c, "supported_targets") && target(&c)
          && TEXT(&c, "required_rescue_api") && exact(&c, 4, 2)
          && exact(&c, 0, 1) && head(&c, 0, &api_minor)
          && api_minor <= UINT32_MAX && c.remaining == 0))
        return PL_MANIFEST_INVALID;

    struct pl_sha256 hash;
    pl_sha256_init(&hash);
    if (pl_sha256_update(&hash, bytes, length) != 0)
        return PL_MANIFEST_INVALID;
    pl_sha256_final(&hash, output->manifest_sha256);

    output->image.profile = PL_TRUSTED_LAN;
    output->image.manifest_version = 1;
    output->image.role = PL_APPLICATION;
    output->image.target.board = PL_PANO_G2;
    output->image.target.revision = PL_REV_B;
    output->image.target.fpga = PL_XC6SLX150_2_FGG484;
    output->image.target.bsp_version = 1;
    output->image.rescue_api_major = 1;
    output->image.rescue_api_min_minor = (uint32_t)api_minor;
    output->image.format = PL_XILINX_SPARTAN6_SPI_V1;
    output->image.required_features = feature_count == 1 ? PL_FEATURE_ICAP_RETURN_V1 : 0;
    output->image.image_length = image_length;
    for (size_t i = 0; i < PL_SHA256_SIZE; ++i)
        output->image.image_sha256[i] = image_digest[i];
    return PL_MANIFEST_OK;
}
