#include "rescue_boot_policy.h"

#include <stddef.h>

static bool journal_state_known(enum rescue_journal_state state)
{
    switch (state) {
    case RESCUE_JOURNAL_STABLE:
    case RESCUE_JOURNAL_TRIAL_PENDING:
    case RESCUE_JOURNAL_TRIAL_RUNNING:
    case RESCUE_JOURNAL_ROLLBACK_REQUIRED:
    case RESCUE_JOURNAL_RECOVERY_ONLY:
        return true;
    default:
        return false;
    }
}

static enum rescue_boot_decision decide(struct rescue_boot_policy *policy,
                                       const struct rescue_boot_inputs *inputs,
                                       uint32_t timeout_ms)
{
    if (inputs == NULL || !inputs->identity_valid || !inputs->journal_valid ||
        !journal_state_known(inputs->journal_state) ||
        timeout_ms < RESCUE_AUTOBOOT_MIN_MS || timeout_ms > RESCUE_AUTOBOOT_MAX_MS) {
        return RESCUE_RECOVERY_ONLY;
    }

    switch (policy->state) {
    case RESCUE_WAIT_FOR_SAMPLE:
        if (!inputs->button_sampled) {
            return RESCUE_WAIT_FOR_SAMPLE;
        }
        if (inputs->journal_state == RESCUE_JOURNAL_TRIAL_RUNNING) {
            return RESCUE_ROLLBACK_TRIAL;
        }
        break;
    case RESCUE_ROLLBACK_TRIAL:
        if (!inputs->button_sampled) {
            return RESCUE_RECOVERY_ONLY;
        }
        if (inputs->journal_state == RESCUE_JOURNAL_TRIAL_RUNNING) {
            return RESCUE_ROLLBACK_TRIAL;
        }
        if (inputs->journal_state != RESCUE_JOURNAL_ROLLBACK_REQUIRED) {
            return RESCUE_RECOVERY_ONLY;
        }
        break;
    case RESCUE_AUTOBOOT_WINDOW:
        if (!inputs->button_sampled || !inputs->time_valid ||
            inputs->now_ms < policy->last_ms ||
            inputs->journal_state == RESCUE_JOURNAL_TRIAL_RUNNING) {
            return RESCUE_RECOVERY_ONLY;
        }
        policy->last_ms = inputs->now_ms;
        break;
    case RESCUE_IDLE:
    case RESCUE_HELD:
        return policy->state;
    default:
        return RESCUE_RECOVERY_ONLY;
    }

    if (inputs->journal_state == RESCUE_JOURNAL_RECOVERY_ONLY) {
        return RESCUE_RECOVERY_ONLY;
    }
    if (policy->hold_latched) {
        return RESCUE_HELD;
    }

    if (policy->state != RESCUE_AUTOBOOT_WINDOW) {
        if (!inputs->confirmed_valid) {
            return RESCUE_IDLE;
        }
        if (!inputs->time_valid || inputs->now_ms > UINT64_MAX - timeout_ms) {
            return RESCUE_RECOVERY_ONLY;
        }
        policy->last_ms = inputs->now_ms;
        policy->deadline_ms = inputs->now_ms + timeout_ms;
        return RESCUE_AUTOBOOT_WINDOW;
    }

    if (inputs->now_ms < policy->deadline_ms) {
        return RESCUE_AUTOBOOT_WINDOW;
    }
    return inputs->confirmed_valid ? RESCUE_BOOT_CONFIRMED : RESCUE_IDLE;
}

enum rescue_boot_decision rescue_boot_step(struct rescue_boot_policy *policy,
                                          const struct rescue_boot_inputs *inputs,
                                          uint32_t timeout_ms)
{
    if (policy == NULL) {
        return RESCUE_RECOVERY_ONLY;
    }
    if (inputs != NULL &&
        (inputs->hold_requested || (inputs->button_sampled && inputs->button_held))) {
        policy->hold_latched = true;
    }
    policy->state = decide(policy, inputs, timeout_ms);
    return policy->state;
}
