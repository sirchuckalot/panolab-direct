#include "rescue_trial.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

enum { SECTOR_BYTES = RESCUE_JOURNAL_RECORD_BYTES + 65 };
enum marker_fault { MARKER_OK, FAIL_BEFORE_MARKER, FAIL_AFTER_MARKER };

static const struct rescue_journal_binding absent;
static const struct rescue_journal_binding image_a = {
    .slot = RESCUE_JOURNAL_A, .digest = {0x12, 0x34}
};
static const struct rescue_journal_binding image_b = {
    .slot = RESCUE_JOURNAL_B, .digest = {0x56, 0x78}
};

struct fixture {
    uint8_t flash[2][SECTOR_BYTES];
    struct rescue_journal_io io;
    struct rescue_trial trial;
    struct rescue_journal_binding stored[3];
    struct rescue_trial_launch live_launch;
    bool healthy_return;
    enum marker_fault fault;
    unsigned writes;
};

static bool same_binding(const struct rescue_journal_binding *a,
                         const struct rescue_journal_binding *b)
{
    return a->slot == b->slot &&
           memcmp(a->digest, b->digest, sizeof a->digest) == 0;
}

static int nor_read(void *context, unsigned sector, size_t offset,
                    uint8_t *data, size_t length)
{
    struct fixture *f = context;
    CHECK(sector < 2 && offset <= SECTOR_BYTES && length <= SECTOR_BYTES - offset);
    memcpy(data, f->flash[sector] + offset, length);
    return 0;
}

static int nor_erase(void *context, unsigned sector)
{
    struct fixture *f = context;
    CHECK(sector < 2);
    ++f->writes;
    memset(f->flash[sector], 0xff, SECTOR_BYTES);
    return 0;
}

static int nor_program(void *context, unsigned sector, size_t offset,
                       const uint8_t *data, size_t length)
{
    struct fixture *f = context;
    const size_t marker = RESCUE_JOURNAL_RECORD_BYTES - 1;
    CHECK(sector < 2);
    CHECK((offset == 0 && length == marker) || (offset == marker && length == 1));
    ++f->writes;
    if (offset == marker && f->fault == FAIL_BEFORE_MARKER)
        return -1;
    for (size_t i = 0; i < length; ++i) {
        uint8_t *byte = &f->flash[sector][offset + i];
        CHECK((*byte & data[i]) == data[i]);
        *byte &= data[i];
    }
    return offset == marker && f->fault == FAIL_AFTER_MARKER ? -1 : 0;
}

static bool verify_image(void *context, const struct rescue_journal_binding *image)
{
    struct fixture *f = context;
    return image->slot <= RESCUE_JOURNAL_B &&
           same_binding(image, &f->stored[image->slot]);
}

static bool verify_return(void *context, const void *evidence,
                          const struct rescue_trial_launch *launch)
{
    struct fixture *f = context;
    return evidence == &f->live_launch && f->healthy_return &&
           launch->sequence == f->live_launch.sequence &&
           same_binding(&launch->image, &f->live_launch.image);
}

static void init(struct fixture *f, const struct rescue_journal_record *record)
{
    *f = (struct fixture){0};
    memset(f->flash, 0xff, sizeof f->flash);
    CHECK(rescue_journal_encode(record, f->flash[0]) == RESCUE_JOURNAL_OK);
    f->stored[RESCUE_JOURNAL_A] = image_a;
    f->stored[RESCUE_JOURNAL_B] = image_b;
    f->io = (struct rescue_journal_io){
        f, SECTOR_BYTES, nor_read, nor_erase, nor_program
    };
    f->trial = (struct rescue_trial){&f->io, f, verify_image, verify_return};
}

static void expect_head(const struct fixture *f, uint64_t sequence, uint8_t state,
                        uint8_t attempts, struct rescue_journal_binding confirmed,
                        struct rescue_journal_binding pending,
                        struct rescue_journal_binding previous)
{
    struct rescue_journal_record head;
    CHECK(rescue_journal_read(&f->io, &head) == RESCUE_JOURNAL_OK);
    CHECK(head.sequence == sequence && head.state == state && head.attempts == attempts);
    CHECK(same_binding(&head.confirmed, &confirmed));
    CHECK(same_binding(&head.pending, &pending));
    CHECK(same_binding(&head.previous, &previous));
}

static const struct rescue_journal_record stable = {
    .sequence = 40, .state = RESCUE_RECORD_STABLE,
    .confirmed = {.slot = RESCUE_JOURNAL_A, .digest = {0x12, 0x34}},
    .reason = "confirmed"
};

static void test_first_install(void)
{
    const struct rescue_journal_record recovery = {
        .sequence = 0, .state = RESCUE_RECORD_RECOVERY_ONLY, .reason = "provisioned"
    };
    struct fixture f;
    init(&f, &recovery);
    CHECK(rescue_trial_prepare(&f.trial, 0, &image_a, false) == RESCUE_TRIAL_OK);
    expect_head(&f, 1, RESCUE_RECORD_TRIAL_PENDING, 1, absent, image_a, absent);

    struct rescue_trial_launch launch;
    CHECK(rescue_trial_start(&f.trial, 1, &launch) == RESCUE_TRIAL_OK);
    expect_head(&f, 2, RESCUE_RECORD_TRIAL_RUNNING, 0, absent, image_a, absent);
    f.live_launch = launch;
    f.healthy_return = true;
    CHECK(rescue_trial_confirm(&f.trial, &launch, &f.live_launch, true) == RESCUE_TRIAL_OK);
    expect_head(&f, 3, RESCUE_RECORD_STABLE, 0, image_a, absent, absent);
}

static void test_update_and_rollback(void)
{
    struct fixture f;
    init(&f, &stable);
    CHECK(rescue_trial_prepare(&f.trial, 40, &image_a, false) == RESCUE_TRIAL_INVALID);
    f.stored[RESCUE_JOURNAL_B].digest[31] ^= 1;
    CHECK(rescue_trial_prepare(&f.trial, 40, &image_b, false) == RESCUE_TRIAL_IMAGE_REJECTED);
    CHECK(f.writes == 0);
    f.stored[RESCUE_JOURNAL_B] = image_b;
    CHECK(rescue_trial_prepare(&f.trial, 40, &image_b, false) == RESCUE_TRIAL_OK);
    expect_head(&f, 41, RESCUE_RECORD_TRIAL_PENDING, 1, image_a, image_b, absent);

    struct rescue_trial_launch launch = {99, image_a};
    f.stored[RESCUE_JOURNAL_B].digest[31] ^= 1;
    CHECK(rescue_trial_start(&f.trial, 41, &launch) == RESCUE_TRIAL_IMAGE_REJECTED);
    CHECK(launch.sequence == 99 && same_binding(&launch.image, &image_a));
    expect_head(&f, 41, RESCUE_RECORD_TRIAL_PENDING, 1, image_a, image_b, absent);

    f.stored[RESCUE_JOURNAL_B] = image_b;
    CHECK(rescue_trial_start(&f.trial, 41, &launch) == RESCUE_TRIAL_OK);
    CHECK(launch.sequence == 42 && same_binding(&launch.image, &image_b));
    expect_head(&f, 42, RESCUE_RECORD_TRIAL_RUNNING, 0, image_a, image_b, absent);
    struct rescue_trial_launch claim = launch;
    const unsigned writes = f.writes;
    CHECK(rescue_trial_start(&f.trial, 42, &claim) == RESCUE_TRIAL_INVALID);
    f.live_launch = launch;
    CHECK(rescue_trial_confirm(&f.trial, &launch, &f.live_launch, true) ==
          RESCUE_TRIAL_CONFIRM_REJECTED);
    f.healthy_return = true;
    CHECK(rescue_trial_confirm(&f.trial, &launch, NULL, true) ==
          RESCUE_TRIAL_CONFIRM_REJECTED);
    CHECK(rescue_trial_confirm(&f.trial, &launch, &claim, true) ==
          RESCUE_TRIAL_CONFIRM_REJECTED);
    CHECK(rescue_trial_confirm(&f.trial, &launch, &f.live_launch, false) ==
          RESCUE_TRIAL_CONFIRM_REJECTED);

    claim.sequence = 41;
    f.live_launch = claim;
    CHECK(rescue_trial_confirm(&f.trial, &claim, &f.live_launch, true) == RESCUE_TRIAL_STALE);
    claim = launch;
    claim.image.digest[31] ^= 1;
    f.live_launch = claim;
    f.stored[RESCUE_JOURNAL_B] = claim.image;
    CHECK(rescue_trial_confirm(&f.trial, &claim, &f.live_launch, true) ==
          RESCUE_TRIAL_CONFIRM_REJECTED);

    f.live_launch = launch;
    CHECK(rescue_trial_confirm(&f.trial, &launch, &f.live_launch, true) ==
          RESCUE_TRIAL_IMAGE_REJECTED);
    CHECK(f.writes == writes);
    expect_head(&f, 42, RESCUE_RECORD_TRIAL_RUNNING, 0, image_a, image_b, absent);

    f.stored[RESCUE_JOURNAL_B] = image_b;
    CHECK(rescue_trial_confirm(&f.trial, &launch, &f.live_launch, true) == RESCUE_TRIAL_OK);
    expect_head(&f, 43, RESCUE_RECORD_STABLE, 0, image_b, absent, image_a);
    CHECK(rescue_trial_confirm(&f.trial, &launch, &f.live_launch, true) == RESCUE_TRIAL_STALE);
    CHECK(rescue_trial_prepare(&f.trial, 43, &image_a, false) == RESCUE_TRIAL_INVALID);
    f.stored[RESCUE_JOURNAL_A].digest[31] ^= 1;
    CHECK(rescue_trial_rollback(&f.trial, 43) == RESCUE_TRIAL_IMAGE_REJECTED);
    expect_head(&f, 43, RESCUE_RECORD_STABLE, 0, image_b, absent, image_a);
    f.stored[RESCUE_JOURNAL_A] = image_a;
    CHECK(rescue_trial_rollback(&f.trial, 43) == RESCUE_TRIAL_OK);
    expect_head(&f, 44, RESCUE_RECORD_STABLE, 0, image_a, absent, image_b);
    CHECK(rescue_trial_prepare(&f.trial, 44, &image_b, true) == RESCUE_TRIAL_OK);
    expect_head(&f, 45, RESCUE_RECORD_TRIAL_PENDING, 1, image_a, image_b, absent);
}

static void test_failed_reset(void)
{
    struct fixture f;
    struct rescue_trial_launch launch;
    init(&f, &stable);
    CHECK(rescue_trial_prepare(&f.trial, 40, &image_b, false) == RESCUE_TRIAL_OK);
    CHECK(rescue_trial_start(&f.trial, 41, &launch) == RESCUE_TRIAL_OK);
    CHECK(rescue_trial_failed_reset(&f.trial, launch.sequence) == RESCUE_TRIAL_OK);
    expect_head(&f, 43, RESCUE_RECORD_ROLLBACK_REQUIRED, 0, image_a, absent, absent);
    CHECK(rescue_trial_start(&f.trial, 43, &launch) == RESCUE_TRIAL_INVALID);
}

static void test_failed_start_commit(void)
{
    for (enum marker_fault fault = FAIL_BEFORE_MARKER; fault <= FAIL_AFTER_MARKER; ++fault) {
        struct fixture f;
        init(&f, &stable);
        CHECK(rescue_trial_prepare(&f.trial, 40, &image_b, false) == RESCUE_TRIAL_OK);
        f.fault = fault;
        struct rescue_trial_launch launch = {99, image_a};
        CHECK(rescue_trial_start(&f.trial, 41, &launch) == RESCUE_TRIAL_IO_ERROR);
        CHECK(launch.sequence == 99 && same_binding(&launch.image, &image_a));
        if (fault == FAIL_BEFORE_MARKER)
            expect_head(&f, 41, RESCUE_RECORD_TRIAL_PENDING, 1, image_a, image_b, absent);
        else
            expect_head(&f, 42, RESCUE_RECORD_TRIAL_RUNNING, 0, image_a, image_b, absent);
    }
}

static void test_sequence_overflow(void)
{
    struct rescue_journal_record head = stable;
    head.sequence = UINT64_MAX - 1;
    struct fixture f;
    init(&f, &head);
    CHECK(rescue_trial_prepare(&f.trial, head.sequence, &image_b, false) == RESCUE_TRIAL_OK);
    const unsigned writes = f.writes;
    struct rescue_trial_launch launch = {99, image_a};
    CHECK(rescue_trial_start(&f.trial, UINT64_MAX, &launch) == RESCUE_TRIAL_OVERFLOW);
    CHECK(launch.sequence == 99 && same_binding(&launch.image, &image_a));
    CHECK(f.writes == writes);
    expect_head(&f, UINT64_MAX, RESCUE_RECORD_TRIAL_PENDING, 1, image_a, image_b, absent);
}

int main(void)
{
    test_first_install();
    test_update_and_rollback();
    test_failed_reset();
    test_failed_start_commit();
    test_sequence_overflow();
    puts("rescue trial tests passed");
    return EXIT_SUCCESS;
}
