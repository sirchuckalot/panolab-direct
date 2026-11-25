/* PanoLab Trusted-LAN manifest parser tests. SPDX-License-Identifier: GPL-3.0-or-later */
#include "manifest_core.h"
#include "build/fixtures.h"

#include <stdio.h>
#include <string.h>

static int failures;

static void expect_failure(const char *name, const uint8_t *bytes, size_t length,
                           enum pl_manifest_result expected)
{
    struct pl_manifest output;
    unsigned char before[sizeof(output)];
    memset(&output, 0xa5, sizeof(output));
    memcpy(before, &output, sizeof(before));

    enum pl_manifest_result result = pl_manifest_parse(bytes, length, &output);
    if (result != expected) {
        fprintf(stderr, "%s (%zu bytes): result %d, expected %d\n",
                name, length, (int)result, (int)expected);
        ++failures;
    }
    if (memcmp(before, &output, sizeof(before)) != 0) {
        fprintf(stderr, "%s (%zu bytes): output changed on failure\n", name, length);
        ++failures;
    }
}

static void expect_valid(const char *name, const uint8_t *bytes, size_t length,
                         const uint8_t *digest, uint64_t image_length,
                         uint32_t api_minor, uint32_t features)
{
    struct pl_manifest output = {0};
    if (pl_manifest_parse(bytes, length, &output) != PL_MANIFEST_OK) {
        fprintf(stderr, "%s: parse failed\n", name);
        ++failures;
        return;
    }

    const struct pl_image_metadata *image = &output.image;
    if (image->profile != PL_TRUSTED_LAN ||
        image->manifest_version != 1u ||
        image->role != PL_APPLICATION ||
        image->target.board != PL_PANO_G2 ||
        image->target.revision != PL_REV_B ||
        image->target.fpga != PL_XC6SLX150_2_FGG484 ||
        image->target.bsp_version != 1u ||
        image->rescue_api_major != 1u ||
        image->rescue_api_min_minor != api_minor ||
        image->format != PL_XILINX_SPARTAN6_SPI_V1 ||
        image->required_features != features ||
        image->image_length != image_length ||
        memcmp(image->image_sha256, fixture_image_digest, PL_SHA256_SIZE) != 0 ||
        memcmp(output.manifest_sha256, digest, PL_SHA256_SIZE) != 0) {
        fprintf(stderr, "%s: metadata or digest mismatch\n", name);
        ++failures;
    }

    for (size_t prefix = 0; prefix < length; ++prefix)
        expect_failure(name, bytes, prefix, prefix == 0 ? PL_MANIFEST_SIZE : PL_MANIFEST_INVALID);
}

#define EXPECT_INVALID(fixture) \
    expect_failure(#fixture, fixture, sizeof(fixture), PL_MANIFEST_INVALID)

int main(void)
{
    expect_valid("valid_manifest", valid_manifest, sizeof(valid_manifest),
                 valid_manifest_digest, UINT64_C(0x100000001), 7, PL_FEATURE_ICAP_RETURN_V1);
    expect_valid("minimal_manifest", minimal_manifest, sizeof(minimal_manifest),
                 minimal_manifest_digest, 1, 0, 0);

    EXPECT_INVALID(reordered_keys);
    EXPECT_INVALID(duplicate_keys);
    EXPECT_INVALID(nonpreferred_uint_1);
    EXPECT_INVALID(nonpreferred_uint_2);
    EXPECT_INVALID(nonpreferred_uint_4);
    EXPECT_INVALID(nonpreferred_uint_8);
    EXPECT_INVALID(wrong_board);
    EXPECT_INVALID(unknown_feature);
    EXPECT_INVALID(signing_fields);
    EXPECT_INVALID(trailing_bytes);
    EXPECT_INVALID(wrong_role);

    uint8_t oversized[PL_MANIFEST_MAX_SIZE + 1u] = {0};
    memcpy(oversized, valid_manifest, sizeof(valid_manifest));
    expect_failure("oversized", oversized, sizeof(oversized), PL_MANIFEST_SIZE);
    expect_failure("null input", NULL, sizeof(valid_manifest), PL_MANIFEST_ARGUMENT);
    if (pl_manifest_parse(valid_manifest, sizeof(valid_manifest), NULL) != PL_MANIFEST_ARGUMENT) {
        fputs("null output: expected argument error\n", stderr);
        ++failures;
    }
    if (failures != 0)
        return 1;
    puts("manifest tests passed");
    return 0;
}
