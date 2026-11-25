#include "rescue_boot_policy.h"
#include <assert.h>
#include <stdio.h>
#include <stddef.h>
static struct rescue_boot_inputs good(void) {
    struct rescue_boot_inputs i = {0};
    i.identity_valid=true; i.journal_valid=true; i.journal_state=RESCUE_JOURNAL_STABLE;
    i.button_sampled=true; i.confirmed_valid=true; i.time_valid=true; i.now_ms=100;
    return i;
}
#define STEP(expected) assert(rescue_boot_step(&p,&i,5000)==(expected))
#define RESET() do { p=(struct rescue_boot_policy){0}; i=good(); } while(0)
int main(void) {
    struct rescue_boot_policy p; struct rescue_boot_inputs i;
    RESET(); i.button_sampled=false; STEP(RESCUE_WAIT_FOR_SAMPLE); i.button_sampled=true; i.button_held=true; STEP(RESCUE_HELD); i.button_held=false; i.now_ms=9000; STEP(RESCUE_HELD);
    RESET(); STEP(RESCUE_AUTOBOOT_WINDOW); i.now_ms=5099; STEP(RESCUE_AUTOBOOT_WINDOW); i.now_ms=5100; STEP(RESCUE_BOOT_CONFIRMED); STEP(RESCUE_RECOVERY_ONLY);
    RESET(); STEP(RESCUE_AUTOBOOT_WINDOW); i.now_ms=5100; i.confirmed_valid=false; STEP(RESCUE_IDLE);
    RESET(); STEP(RESCUE_AUTOBOOT_WINDOW); i.hold_requested=true; STEP(RESCUE_HELD);
    RESET(); i.identity_valid=false; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); i.journal_valid=false; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); i.journal_state=RESCUE_JOURNAL_UNKNOWN; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); i.journal_state=RESCUE_JOURNAL_RECOVERY_ONLY; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); i.confirmed_valid=false; STEP(RESCUE_IDLE);
    RESET(); i.time_valid=false; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); i.now_ms=UINT64_MAX-4999; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); STEP(RESCUE_AUTOBOOT_WINDOW); i.now_ms=99; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); i.journal_state=RESCUE_JOURNAL_TRIAL_RUNNING; STEP(RESCUE_ROLLBACK_TRIAL); STEP(RESCUE_ROLLBACK_TRIAL); i.journal_state=RESCUE_JOURNAL_ROLLBACK_REQUIRED; STEP(RESCUE_AUTOBOOT_WINDOW);
    RESET(); i.journal_state=RESCUE_JOURNAL_TRIAL_RUNNING; STEP(RESCUE_ROLLBACK_TRIAL); i.journal_state=RESCUE_JOURNAL_STABLE; STEP(RESCUE_RECOVERY_ONLY);
    RESET(); assert(rescue_boot_step(&p,&i,0)==RESCUE_RECOVERY_ONLY);
    RESET(); assert(rescue_boot_step(&p,&i,RESCUE_AUTOBOOT_MAX_MS+1)==RESCUE_RECOVERY_ONLY);
    RESET(); assert(rescue_boot_step(&p,NULL,5000)==RESCUE_RECOVERY_ONLY);
    RESET(); assert(rescue_boot_step(NULL,&i,5000)==RESCUE_RECOVERY_ONLY);
    RESET();
    assert(rescue_boot_step(&p, &i, 999) == RESCUE_RECOVERY_ONLY);
    RESET();
    assert(rescue_boot_step(&p, &i, 1000) == RESCUE_AUTOBOOT_WINDOW);
    RESET();
    assert(rescue_boot_step(&p, &i, 60000) == RESCUE_AUTOBOOT_WINDOW);
    i.now_ms = 60099;
    assert(rescue_boot_step(&p, &i, 60000) == RESCUE_AUTOBOOT_WINDOW);
    i.now_ms = 60100;
    assert(rescue_boot_step(&p, &i, 60000) == RESCUE_BOOT_CONFIRMED);
    assert(rescue_boot_step(&p, &i, 60000) == RESCUE_RECOVERY_ONLY);
    RESET();
    assert(rescue_boot_step(&p, &i, 60001) == RESCUE_RECOVERY_ONLY);
    puts("PASS: boot policy scenarios including 1 s and 60 s boundaries");
    return 0;
}
