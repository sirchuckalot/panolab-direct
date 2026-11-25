/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PL_STREAM_SLOT_H
#define PL_STREAM_SLOT_H

#include "rescue_update.h"
#include "../upload-session/upload_session.h"

/* Internal backend state. Initialize using pl_stream_slot_init. */
struct pl_stream_slot {
    const struct rescue_update *update;
    enum rescue_slot target;
    uint64_t id;
    uint32_t received;
    uint32_t programmed;
    size_t manifest_length;
    struct pl_manifest manifest;
    uint8_t manifest_bytes[PL_MANIFEST_MAX_SIZE];
    uint8_t head[RESCUE_JOURNAL_RECORD_BYTES];
    uint8_t page[256];
    bool started;
    bool failed;
    bool binding_valid;
};

/* SIMULATED NOR ONLY. The server selects target and supplies trusted update
 * configuration and journal sequence. Hold exclusive access to simulated
 * flash, journal and boot state from init through seal/cancel, including
 * callbacks and any binding retrieval. Keep the configuration stable.
 * After PL_UPLOAD_LOCKED, recover storage before initializing again.
 */
enum pl_upload_result pl_stream_slot_init(struct pl_upload_session *session,
    struct pl_stream_slot *slot, const struct rescue_update *update,
    enum rescue_slot target, uint64_t last_id);

/* Retrieve the binding for a successfully sealed upload. The caller owns
 * any later journal operation and must reverify according to its policy.
 */
bool pl_stream_slot_binding(const struct pl_stream_slot *slot,
    uint64_t id, struct rescue_journal_binding *binding);

#endif
