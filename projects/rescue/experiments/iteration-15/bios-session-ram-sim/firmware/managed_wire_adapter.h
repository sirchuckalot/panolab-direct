/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PL_MANAGED_WIRE_ADAPTER_H
#define PL_MANAGED_WIRE_ADAPTER_H
#include "management_wire.h"
/* Simulation only; one instance, one cooperative owner. No reset recovery. */
struct wire_session { uint32_t id, offset; enum mw_state state; int locked; };
extern const struct mw_callbacks managed_wire_callbacks;
#endif
