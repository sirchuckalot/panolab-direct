/* PanoLab image integrity core. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PANOLAB_IMAGE_CORE_H
#define PANOLAB_IMAGE_CORE_H

#include <stddef.h>
#include <stdint.h>

#define PL_SHA256_SIZE 32u
#define PL_IMAGE_READ_CHUNK 256u

struct pl_sha256 {
    uint32_t state[8];
    uint64_t length;
    uint8_t block[64];
    size_t used;
};

void pl_sha256_init(struct pl_sha256 *ctx);
/* Returns 0 on success, -1 if the FIPS bit-length limit would be exceeded. */
int pl_sha256_update(struct pl_sha256 *ctx, const void *data, size_t length);
/* Finalization consumes the context. Initialize it again before reuse. */
void pl_sha256_final(struct pl_sha256 *ctx, uint8_t digest[PL_SHA256_SIZE]);

enum pl_image_profile { PL_TRUSTED_LAN = 1, PL_DEVELOPER, PL_PRODUCTION };
enum pl_image_role { PL_APPLICATION = 1, PL_RESCUE };
enum pl_board { PL_PANO_G2 = 1 };
enum pl_board_revision { PL_REV_B = 1 };
enum pl_fpga { PL_XC6SLX150_2_FGG484 = 1 };
enum pl_config_format { PL_XILINX_SPARTAN6_SPI_V1 = 1 };
#define PL_FEATURE_ICAP_RETURN_V1 UINT32_C(1)

struct pl_target {
    enum pl_board board;
    enum pl_board_revision revision;
    enum pl_fpga fpga;
    uint32_t bsp_version;
};

struct pl_image_metadata {
    enum pl_image_profile profile;
    uint32_t manifest_version;
    enum pl_image_role role;
    struct pl_target target;
    uint32_t rescue_api_major;
    uint32_t rescue_api_min_minor;
    enum pl_config_format format;
    uint32_t required_features;
    uint64_t image_length;
    uint8_t image_sha256[PL_SHA256_SIZE];
};

struct pl_image_policy {
    enum pl_image_profile profile;
    /* Supplied by the caller from verified board/FPGA identity and its BSP. */
    struct pl_target detected_target;
    uint32_t rescue_api_major;
    uint32_t rescue_api_minor;
    uint32_t supported_features;
    uint64_t max_image_length;
};

/* Offsets are relative to the raw image. Fill exactly count bytes and return
 * count on success. Return a different value on failure, including short reads.
 */
typedef size_t (*pl_image_read_fn)(void *context, uint64_t offset,
                                   uint8_t *buffer, size_t count);

enum pl_image_result {
    PL_IMAGE_OK = 0,
    PL_IMAGE_ARGUMENT,
    PL_IMAGE_PROFILE,
    PL_IMAGE_VERSION,
    PL_IMAGE_ROLE,
    PL_IMAGE_TARGET,
    PL_IMAGE_API,
    PL_IMAGE_FORMAT,
    PL_IMAGE_FEATURE,
    PL_IMAGE_LENGTH,
    PL_IMAGE_READ,
    PL_IMAGE_DIGEST
};

/* raw_length is the caller-observed unpadded length. The metadata and policy
 * must remain stable during verification. Trusted-LAN integrity only.
 */
enum pl_image_result pl_image_verify(const struct pl_image_metadata *metadata,
                                     const struct pl_image_policy *policy,
                                     uint64_t raw_length,
                                     pl_image_read_fn read, void *context);

#endif
