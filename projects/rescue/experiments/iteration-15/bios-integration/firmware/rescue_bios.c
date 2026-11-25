#include <stdio.h>

#include <generated/csr.h>
#include <generated/soc.h>

#include "rescue_bios.h"
#include "rescue_boot_policy.h"

#if !defined(CONFIG_BIOS_NO_BOOT) || defined(BIOS_CONSOLE_DISABLE)
#error "Rescue diagnostics require stock boot disabled and the console enabled"
#endif

#define RESCUE_TIMEOUT_MS (PANOLAB_AUTOBOOT_WINDOW_S * UINT32_C(1000))
_Static_assert(RESCUE_TIMEOUT_MS >= RESCUE_AUTOBOOT_MIN_MS &&
               RESCUE_TIMEOUT_MS <= RESCUE_AUTOBOOT_MAX_MS,
               "Rescue timeout outside policy domain");

void rescue_bios_diagnose(void)
{
    struct rescue_boot_policy policy = {0};
    /* Verification and the policy's monotonic time source are unavailable. */
    struct rescue_boot_inputs inputs = {0};

    /* One volatile CSR read per poll. Bound the wait even if sampled is stuck. */
    for (uint32_t poll = 0; poll < PANOLAB_BUTTON_POLL_LIMIT; ++poll) {
        if (rescue_button_sampled_read()) {
            inputs.button_sampled = true;
            inputs.button_held = rescue_button_held_latched_read() != 0;
            break;
        }
    }

    enum rescue_boot_decision decision =
        rescue_boot_step(&policy, &inputs, RESCUE_TIMEOUT_MS);

    puts("Rescue: RECOVERY ONLY (diagnostic BIOS)");
    puts("Rescue: no validated identity, journal, or application slot");
    if (inputs.button_sampled)
        puts(inputs.button_held ? "Rescue: startup button held"
                               : "Rescue: startup button released");
    else
        puts("Rescue: startup button sampling timed out");
    puts(decision == RESCUE_RECOVERY_ONLY
         ? "Rescue: policy returned RECOVERY ONLY"
         : "Rescue: unexpected policy result; forcing RECOVERY ONLY");
    puts("Rescue: application boot disabled; UART console ready");
}
