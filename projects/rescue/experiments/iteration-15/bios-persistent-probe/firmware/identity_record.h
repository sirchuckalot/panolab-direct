/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PANOLAB_IDENTITY_RECORD_H
#define PANOLAB_IDENTITY_RECORD_H
#include "rescue_storage.h"
#define PANOLAB_IDENTITY_RECORD_BYTES 191u
/* Proposed normalized PLID v1 wire record, not the factory record format.
 * No offsets or provisioning operations. Output unchanged on failure. */
bool rescue_identity_decode(const uint8_t *data,size_t n,const struct rescue_mac *inventory,size_t count,struct rescue_identity *out);
#endif
