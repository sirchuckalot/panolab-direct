/* PanoLab Trusted-LAN manifest parser. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PANOLAB_MANIFEST_CORE_H
#define PANOLAB_MANIFEST_CORE_H

#include "image_core.h"

#define PL_MANIFEST_MAX_SIZE 2048u
#define PL_MANIFEST_MAX_TEXT 96u
#define PL_MANIFEST_MAX_PINS 12u

struct pl_manifest {
    struct pl_image_metadata image;
    uint8_t manifest_sha256[PL_SHA256_SIZE];
};

enum pl_manifest_result {
    PL_MANIFEST_OK = 0,
    PL_MANIFEST_ARGUMENT,
    PL_MANIFEST_SIZE,
    PL_MANIFEST_INVALID
};

/* Input must remain stable during the call and must not overlap output.
 * The output is written only on success.
 */
enum pl_manifest_result pl_manifest_parse(const uint8_t *bytes, size_t length,
                                          struct pl_manifest *output);

#endif
