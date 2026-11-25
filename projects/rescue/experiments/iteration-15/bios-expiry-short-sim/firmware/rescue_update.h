/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef RESCUE_UPDATE_H
#define RESCUE_UPDATE_H
#include "rescue_flash_transaction.h"
#include "manifest_store.h"
#include "rescue_trial.h"
struct rescue_update {
 const struct rescue_flash_io *flash;
 const struct rescue_flash_geometry *geometry;
 const struct rescue_region *regions;
 size_t count;
 const struct pl_image_policy *policy;
 bool identity_verified, in_rescue; /* Trusted BSP state, never client data. */
};
enum update_result { UPDATE_OK, UPDATE_INVALID, UPDATE_PROTECTED, UPDATE_STALE,
 UPDATE_IMAGE, UPDATE_IO, UPDATE_JOURNAL, UPDATE_METADATA };
/* Caller serializes all operations and keeps source and policy stable.
 * A failed metadata commit may be ambiguous: reread/reverify before any
 * retry; no binding is returned on failure. Never infer activation from a
 * commit marker alone.
 * Last erase sector of each APP is reserved for metadata (proposed layout). */
enum update_result rescue_update_stage(const struct rescue_update *u,
 const struct rescue_journal_record *expected, enum rescue_slot target,
 const uint8_t *manifest,size_t manifest_length,uint64_t raw_length,
 pl_image_read_fn read,void *context,struct rescue_journal_binding *binding);
bool rescue_update_verify(const struct rescue_update *u,const struct rescue_journal_binding *binding);
enum rescue_trial_result rescue_update_prepare(const struct rescue_update *u,uint64_t seq,const struct rescue_journal_binding *binding);
enum rescue_trial_result rescue_update_start(const struct rescue_update *u,uint64_t seq,struct rescue_trial_launch *launch);
typedef bool (*rescue_return_verifier)(void *context,const void *evidence,const struct rescue_trial_launch *claim);
enum rescue_trial_result rescue_update_confirm(const struct rescue_update *u,const struct rescue_trial_launch *claim,const void *evidence,bool approved,rescue_return_verifier verify_return,void *context);
enum rescue_trial_result rescue_update_failed_reset(const struct rescue_update *u,uint64_t seq);
enum rescue_trial_result rescue_update_rollback(const struct rescue_update *u,uint64_t seq);
#endif
