#ifndef RESCUE_TRIAL_H
#define RESCUE_TRIAL_H

#include <stdbool.h>
#include "rescue_journal.h"

struct rescue_trial_launch {
    uint64_t sequence;
    struct rescue_journal_binding image;
};

struct rescue_trial {
    const struct rescue_journal_io *journal;
    void *context;

    /*
     * Return true only after verifying the current stored canonical manifest
     * digest against image->digest and validating the manifest policy,
     * compatibility, and hash of the raw image read from image->slot.
     * Any verification or storage error must return false.
     */
    bool (*verify_image)(void *context,
                         const struct rescue_journal_binding *image);

    /*
     * BSP contract. Return true only for a trusted live return with observed
     * health from the specified launch. Evidence is opaque to this core.
     * Persisted metadata, a caller-supplied tuple, or a reset alone cannot
     * establish live return. The BSP must supply this implementation.
     */
    bool (*verify_return)(void *context, const void *evidence,
                          const struct rescue_trial_launch *launch);
};

enum rescue_trial_result {
    RESCUE_TRIAL_OK = RESCUE_JOURNAL_OK,
    RESCUE_TRIAL_INVALID = RESCUE_JOURNAL_INVALID,
    RESCUE_TRIAL_IO_ERROR = RESCUE_JOURNAL_IO_ERROR,
    RESCUE_TRIAL_NO_RECORD = RESCUE_JOURNAL_NO_RECORD,
    RESCUE_TRIAL_AMBIGUOUS = RESCUE_JOURNAL_AMBIGUOUS,
    RESCUE_TRIAL_STALE = RESCUE_JOURNAL_STALE,
    RESCUE_TRIAL_OVERFLOW = RESCUE_JOURNAL_OVERFLOW,
    RESCUE_TRIAL_JOURNAL_VERIFY_ERROR = RESCUE_JOURNAL_VERIFY_ERROR,
    RESCUE_TRIAL_IMAGE_REJECTED,
    RESCUE_TRIAL_CONFIRM_REJECTED
};

/*
 * Caller serializes lifecycle, journal, and slot access. Keep verified image
 * bytes unchanged through use of a launch descriptor. Callbacks must not
 * mutate lifecycle state. A commit error can leave a new head installed.
 * Reread before deciding how to recover.
 */
enum rescue_trial_result rescue_trial_prepare(
    const struct rescue_trial *trial, uint64_t expected_sequence,
    const struct rescue_journal_binding *candidate, bool release_previous);

/* On failure launch is unchanged. Use the descriptor only on success. */
enum rescue_trial_result rescue_trial_start(
    const struct rescue_trial *trial, uint64_t expected_sequence,
    struct rescue_trial_launch *launch);

enum rescue_trial_result rescue_trial_confirm(
    const struct rescue_trial *trial, const struct rescue_trial_launch *claim,
    const void *evidence, bool approved);

/* Call on reset after classifying the running trial as unconfirmed. */
enum rescue_trial_result rescue_trial_failed_reset(
    const struct rescue_trial *trial, uint64_t expected_sequence);

/* Cancel a trial or explicitly select the verified retained image. */
enum rescue_trial_result rescue_trial_rollback(
    const struct rescue_trial *trial, uint64_t expected_sequence);

#endif
