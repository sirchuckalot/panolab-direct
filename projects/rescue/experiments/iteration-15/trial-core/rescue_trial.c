#include "rescue_trial.h"

static enum rescue_trial_result read_head(
    const struct rescue_trial *trial, uint64_t expected_sequence,
    struct rescue_journal_record *head)
{
    if (!trial)
        return RESCUE_TRIAL_INVALID;
    const enum rescue_journal_result result =
        rescue_journal_read(trial->journal, head);
    if (result != RESCUE_JOURNAL_OK)
        return (enum rescue_trial_result)result;
    if (head->sequence != expected_sequence)
        return RESCUE_TRIAL_STALE;
    if (head->sequence == UINT64_MAX)
        return RESCUE_TRIAL_OVERFLOW;
    return RESCUE_TRIAL_OK;
}

static enum rescue_trial_result commit(
    const struct rescue_trial *trial, const struct rescue_journal_record *head,
    struct rescue_journal_record *next, const char *reason)
{
    size_t i = 0;
    for (; reason[i]; ++i)
        next->reason[i] = reason[i];
    for (; i < sizeof next->reason; ++i)
        next->reason[i] = '\0';
    next->sequence = head->sequence + 1u;
    return (enum rescue_trial_result)rescue_journal_commit(trial->journal, head, next);
}

static bool is_trial(const struct rescue_journal_record *head)
{
    return head->state == RESCUE_RECORD_TRIAL_PENDING ||
           head->state == RESCUE_RECORD_TRIAL_RUNNING;
}

static bool same_image(const struct rescue_journal_binding *a,
                       const struct rescue_journal_binding *b)
{
    if (a->slot != b->slot)
        return false;
    for (size_t i = 0; i < sizeof a->digest; ++i) {
        if (a->digest[i] != b->digest[i])
            return false;
    }
    return true;
}

static bool verified(const struct rescue_trial *trial,
                     const struct rescue_journal_binding *image)
{
    return image->slot != RESCUE_JOURNAL_NONE && trial->verify_image &&
           trial->verify_image(trial->context, image);
}

enum rescue_trial_result rescue_trial_prepare(
    const struct rescue_trial *trial, uint64_t expected_sequence,
    const struct rescue_journal_binding *candidate, bool release_previous)
{
    if (!candidate || (candidate->slot != RESCUE_JOURNAL_A &&
                       candidate->slot != RESCUE_JOURNAL_B))
        return RESCUE_TRIAL_INVALID;
    struct rescue_journal_record head;
    const enum rescue_trial_result result = read_head(trial, expected_sequence, &head);
    if (result != RESCUE_TRIAL_OK)
        return result;
    if (is_trial(&head) || candidate->slot == head.confirmed.slot ||
        (candidate->slot == head.previous.slot && !release_previous))
        return RESCUE_TRIAL_INVALID;
    if (!verified(trial, candidate))
        return RESCUE_TRIAL_IMAGE_REJECTED;

    struct rescue_journal_record next = head;
    next.pending = *candidate;
    next.previous = (struct rescue_journal_binding){0};
    next.attempts = 1;
    next.state = RESCUE_RECORD_TRIAL_PENDING;
    return commit(trial, &head, &next, "trial_prepared");
}

enum rescue_trial_result rescue_trial_start(
    const struct rescue_trial *trial, uint64_t expected_sequence,
    struct rescue_trial_launch *launch)
{
    if (!launch)
        return RESCUE_TRIAL_INVALID;
    struct rescue_journal_record head;
    enum rescue_trial_result result = read_head(trial, expected_sequence, &head);
    if (result != RESCUE_TRIAL_OK)
        return result;
    if (head.state != RESCUE_RECORD_TRIAL_PENDING)
        return RESCUE_TRIAL_INVALID;
    if (!verified(trial, &head.pending))
        return RESCUE_TRIAL_IMAGE_REJECTED;

    struct rescue_journal_record next = head;
    next.attempts = 0;
    next.state = RESCUE_RECORD_TRIAL_RUNNING;
    result = commit(trial, &head, &next, "trial_started");
    if (result == RESCUE_TRIAL_OK) {
        launch->sequence = next.sequence;
        launch->image = next.pending;
    }
    return result;
}

enum rescue_trial_result rescue_trial_confirm(
    const struct rescue_trial *trial, const struct rescue_trial_launch *claim,
    const void *evidence, bool approved)
{
    if (!trial || !approved || !claim || !evidence || !trial->verify_return)
        return RESCUE_TRIAL_CONFIRM_REJECTED;
    struct rescue_journal_record head;
    const enum rescue_trial_result result = read_head(trial, claim->sequence, &head);
    if (result != RESCUE_TRIAL_OK)
        return result;
    if (head.state != RESCUE_RECORD_TRIAL_RUNNING ||
        !same_image(&head.pending, &claim->image) ||
        !trial->verify_return(trial->context, evidence, claim))
        return RESCUE_TRIAL_CONFIRM_REJECTED;
    if (!verified(trial, &head.pending))
        return RESCUE_TRIAL_IMAGE_REJECTED;

    struct rescue_journal_record next = head;
    next.confirmed = head.pending;
    next.previous = head.confirmed;
    next.pending = (struct rescue_journal_binding){0};
    next.state = RESCUE_RECORD_STABLE;
    return commit(trial, &head, &next, "trial_confirmed");
}

static enum rescue_trial_result discard_trial(
    const struct rescue_trial *trial, const struct rescue_journal_record *head,
    const char *reason)
{
    struct rescue_journal_record next = *head;
    next.pending = (struct rescue_journal_binding){0};
    next.attempts = 0;
    next.state = RESCUE_RECORD_ROLLBACK_REQUIRED;
    return commit(trial, head, &next, reason);
}

enum rescue_trial_result rescue_trial_failed_reset(
    const struct rescue_trial *trial, uint64_t expected_sequence)
{
    struct rescue_journal_record head;
    const enum rescue_trial_result result = read_head(trial, expected_sequence, &head);
    if (result != RESCUE_TRIAL_OK)
        return result;
    if (head.state != RESCUE_RECORD_TRIAL_RUNNING)
        return RESCUE_TRIAL_INVALID;
    return discard_trial(trial, &head, "unconfirmed_trial");
}

enum rescue_trial_result rescue_trial_rollback(
    const struct rescue_trial *trial, uint64_t expected_sequence)
{
    struct rescue_journal_record head;
    const enum rescue_trial_result result = read_head(trial, expected_sequence, &head);
    if (result != RESCUE_TRIAL_OK)
        return result;
    if (is_trial(&head))
        return discard_trial(trial, &head, "explicit_rollback");
    if (head.state == RESCUE_RECORD_RECOVERY_ONLY ||
        head.previous.slot == RESCUE_JOURNAL_NONE)
        return RESCUE_TRIAL_INVALID;
    if (!verified(trial, &head.previous))
        return RESCUE_TRIAL_IMAGE_REJECTED;

    struct rescue_journal_record next = head;
    next.confirmed = head.previous;
    next.previous = head.confirmed;
    next.state = RESCUE_RECORD_STABLE;
    return commit(trial, &head, &next, "explicit_rollback");
}
