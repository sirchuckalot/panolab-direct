/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef PL_MANAGED_STREAM_H
#define PL_MANAGED_STREAM_H

#include "stream_slot.h"

/* One facade per process, initialized once with stable BSP configuration.
 * All calls run on one cooperative event loop. Give the facade exclusive
 * use of the flash driver, including no concurrent SPI clients or direct
 * calls into legacy flash/update APIs. Callbacks are synchronous.
 *
 * Chunk checks compare both raw journal headers. Full journal reads at
 * transaction boundaries validate journal padding and select the head.
 * Physical tampering is outside the ownership guarantee. A failed abort
 * locks the facade for its lifetime. This API makes no reset recovery claim.
 */
enum pl_upload_result pl_managed_init(const struct rescue_update *update,
    enum rescue_slot target, uint64_t last_id);
enum pl_upload_result pl_managed_begin(uint64_t id, uint64_t expected_sequence,
    const uint8_t *manifest, size_t length);
enum pl_upload_result pl_managed_append(uint64_t id, uint64_t offset,
    const uint8_t *bytes, size_t length);
enum pl_upload_result pl_managed_seal(uint64_t id);
enum pl_upload_result pl_managed_cancel(uint64_t id);
bool pl_managed_binding(uint64_t id, struct rescue_journal_binding *binding);

/* These operations require an idle, unlocked facade. A denied request
 * returns INVALID or false and leaves output parameters unchanged.
 */
enum rescue_journal_result pl_managed_journal_read(struct rescue_journal_record *head);
bool pl_managed_verify(const struct rescue_journal_binding *binding);
enum rescue_trial_result pl_managed_prepare(uint64_t seq,
    const struct rescue_journal_binding *binding);
enum rescue_trial_result pl_managed_start(uint64_t seq, struct rescue_trial_launch *launch);
enum rescue_trial_result pl_managed_confirm(const struct rescue_trial_launch *claim,
    const void *evidence, bool approved, rescue_return_verifier verifier, void *context);
enum rescue_trial_result pl_managed_failed_reset(uint64_t seq);
enum rescue_trial_result pl_managed_rollback(uint64_t seq);

#endif
