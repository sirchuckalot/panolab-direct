/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PL_SIM_UPLOAD_H
#define PL_SIM_UPLOAD_H
#include "rescue_storage.h"
#include "network_session.h"
#include <stddef.h>
#include <stdint.h>
bool sim_upload_init(const struct rescue_flash_geometry *geometry);
bool sim_upload_session_init(ns_clock_fn clock, ns_reply_fn reply);
void sim_upload_receive(const struct ns_peer *peer,const uint8_t *data,size_t length);
void sim_upload_tick(void);
#endif
