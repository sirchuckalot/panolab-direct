#ifndef RESCUE_BOOT_POLICY_H
#define RESCUE_BOOT_POLICY_H

#include <stdbool.h>
#include <stdint.h>

#define RESCUE_AUTOBOOT_MIN_MS UINT32_C(1000)
#define RESCUE_AUTOBOOT_DEFAULT_MS UINT32_C(5000)
#define RESCUE_AUTOBOOT_MAX_MS UINT32_C(60000)

enum rescue_journal_state {
    RESCUE_JOURNAL_UNKNOWN = 0,
    RESCUE_JOURNAL_STABLE,
    RESCUE_JOURNAL_TRIAL_PENDING,
    RESCUE_JOURNAL_TRIAL_RUNNING,
    RESCUE_JOURNAL_ROLLBACK_REQUIRED,
    RESCUE_JOURNAL_RECOVERY_ONLY
};

enum rescue_boot_decision {
    RESCUE_WAIT_FOR_SAMPLE = 0,
    RESCUE_RECOVERY_ONLY,
    RESCUE_HELD,
    RESCUE_IDLE,
    RESCUE_ROLLBACK_TRIAL,
    RESCUE_AUTOBOOT_WINDOW,
    RESCUE_BOOT_CONFIRMED
};

struct rescue_boot_inputs {
    bool identity_valid;
    bool journal_valid;
    enum rescue_journal_state journal_state;
    bool button_sampled;
    bool button_held;
    bool confirmed_valid;
    bool time_valid;
    uint64_t now_ms;
    bool hold_requested;
};

/* Zero-initialize once per Rescue startup. Members belong to the core. */
struct rescue_boot_policy {
    enum rescue_boot_decision state;
    uint64_t last_ms;
    uint64_t deadline_ms;
    bool hold_latched;
};

/*
 * Supply fresh verification results on every call. confirmed_valid must refer
 * to the confirmed slot and digest in the current verified journal record.
 * button_held is the latched result of the completed startup sampling window.
 * Time uses a nonwrapping monotonic millisecond counter. Pass a timeout in
 * [RESCUE_AUTOBOOT_MIN_MS, RESCUE_AUTOBOOT_MAX_MS]
 * on every call. It is captured when the window opens.
 *
 * RESCUE_ROLLBACK_TRIAL requests durable discard of an unconfirmed running
 * trial. Once verified, present the committed ROLLBACK_REQUIRED record.
 * A hold request is latched even while waiting for sampling or rollback.
 *
 * RESCUE_BOOT_CONFIRMED is a one-shot decision. Consume it using the same
 * verified snapshot submitted at the deadline. A later call returns recovery.
 */
enum rescue_boot_decision rescue_boot_step(struct rescue_boot_policy *policy,
                                          const struct rescue_boot_inputs *inputs,
                                          uint32_t timeout_ms);

#endif
