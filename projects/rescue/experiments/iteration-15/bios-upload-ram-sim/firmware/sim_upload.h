/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PL_SIM_UPLOAD_H
#define PL_SIM_UPLOAD_H
#include "rescue_storage.h"
#include <stddef.h>
#include <stdint.h>
bool sim_upload_init(const struct rescue_flash_geometry *geometry);
size_t sim_upload_request(const uint8_t *data,size_t length,uint8_t *reply,size_t capacity);
#endif
