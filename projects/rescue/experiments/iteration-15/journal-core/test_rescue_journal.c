#include "rescue_journal.h"
#include "../bios-integration/firmware/rescue_boot_policy.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do { \
    if (!(condition)) { \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

enum {
    SECTOR_BYTES = RESCUE_JOURNAL_RECORD_BYTES + 65,
    BODY_BYTES = RESCUE_JOURNAL_RECORD_BYTES - 1,
    READS_PER_VALID_SECTOR = 4,
    HEAD_READS = 2 * READS_PER_VALID_SECTOR
};

enum fault { NONE, ERASE, BODY, MARKER, READ, BAD_READ };

struct flash {
    uint8_t sectors[2][SECTOR_BYTES];
    enum fault fault;
    size_t cut;
    size_t reads;
    unsigned mutations;
    unsigned target;
    int marker_written;
};

static int sim_read(void *context, unsigned sector, size_t offset,
                    uint8_t *data, size_t length)
{
    struct flash *flash = context;
    CHECK(sector < 2 && offset <= SECTOR_BYTES &&
          length <= SECTOR_BYTES - offset);
    ++flash->reads;
    if (flash->fault == READ && flash->reads == flash->cut)
        return -1;
    memcpy(data, flash->sectors[sector] + offset, length);
    if (flash->fault == BAD_READ && flash->reads == flash->cut)
        data[0] ^= 1u;
    return 0;
}

static int sim_erase(void *context, unsigned sector)
{
    struct flash *flash = context;
    CHECK(sector == flash->target);
    ++flash->mutations;
    const size_t count = flash->fault == ERASE ? flash->cut : SECTOR_BYTES;
    memset(flash->sectors[sector], 0xff, count);
    return flash->fault == ERASE ? -1 : 0;
}

static int sim_program(void *context, unsigned sector, size_t offset,
                       const uint8_t *data, size_t length)
{
    struct flash *flash = context;
    CHECK(sector == flash->target);
    CHECK((offset == 0 && length == BODY_BYTES) ||
          (offset == BODY_BYTES && length == 1));
    ++flash->mutations;
    if (offset == BODY_BYTES && flash->fault == MARKER) {
        CHECK(data[0] == 0 && flash->sectors[sector][offset] == UINT8_MAX);
        flash->sectors[sector][offset] = (uint8_t)(UINT8_MAX << flash->cut);
        flash->marker_written = flash->cut == 8;
        return -1;
    }
    const int cut_body = offset == 0 && flash->fault == BODY;
    const size_t count = cut_body ? flash->cut : length;
    for (size_t i = 0; i < count; ++i) {
        uint8_t *byte = &flash->sectors[sector][offset + i];
        CHECK((*byte & data[i]) == data[i]);
        *byte &= data[i];
    }
    flash->marker_written = offset == BODY_BYTES;
    return cut_body ? -1 : 0;
}

static struct rescue_journal_io journal_io(struct flash *flash)
{
    return (struct rescue_journal_io){
        flash, SECTOR_BYTES, sim_read, sim_erase, sim_program
    };
}

static struct rescue_journal_record record(uint64_t sequence)
{
    return (struct rescue_journal_record){
        .sequence = sequence,
        .confirmed = { .slot = RESCUE_JOURNAL_A, .digest = { 0xab } },
        .state = RESCUE_RECORD_STABLE,
        .reason = "confirmed"
    };
}

static void seed(struct flash *flash, unsigned sector,
                 const struct rescue_journal_record *value)
{
    CHECK(rescue_journal_encode(value, flash->sectors[sector]) == RESCUE_JOURNAL_OK);
}

static struct flash fixture(unsigned active)
{
    struct flash flash = { .target = 1u - active };
    const struct rescue_journal_record older = record(40);
    const struct rescue_journal_record current = record(41);
    memset(flash.sectors, 0xff, sizeof flash.sectors);
    seed(&flash, flash.target, &older);
    seed(&flash, active, &current);
    return flash;
}

static void expect_head(const struct rescue_journal_io *io,
                        const struct rescue_journal_record *expected)
{
    struct rescue_journal_record actual;
    uint8_t expected_frame[RESCUE_JOURNAL_RECORD_BYTES];
    uint8_t actual_frame[RESCUE_JOURNAL_RECORD_BYTES];
    CHECK(rescue_journal_read(io, &actual) == RESCUE_JOURNAL_OK);
    CHECK(rescue_journal_encode(expected, expected_frame) == RESCUE_JOURNAL_OK);
    CHECK(rescue_journal_encode(&actual, actual_frame) == RESCUE_JOURNAL_OK);
    CHECK(memcmp(actual_frame, expected_frame, sizeof actual_frame) == 0);
}

static unsigned test_faults(void)
{
    const struct rescue_journal_record current = record(41);
    struct rescue_journal_record next = record(42);
    next.state = RESCUE_RECORD_TRIAL_PENDING;
    next.pending.slot = RESCUE_JOURNAL_B;
    next.pending.digest[0] = 0xcd;
    next.attempts = 1;
    strcpy(next.reason, "trial");
    unsigned cases = 0;

    for (unsigned active = 0; active < 2; ++active) {
        struct flash successful = fixture(active);
        struct rescue_journal_io io = journal_io(&successful);
        CHECK(rescue_journal_commit(&io, &current, &next) == RESCUE_JOURNAL_OK);
        const size_t reads = successful.reads;
        CHECK(reads == 2 * HEAD_READS + READS_PER_VALID_SECTOR);
        CHECK(successful.mutations == 3 && successful.marker_written);
        expect_head(&io, &next);

        for (enum fault fault = ERASE; fault <= READ; ++fault) {
            const size_t first = fault == READ ? 1 : 0;
            const size_t last = fault == READ ? reads :
                                fault == ERASE ? SECTOR_BYTES :
                                fault == BODY ? BODY_BYTES : 8;
            for (size_t cut = first; cut <= last; ++cut) {
                struct flash flash = fixture(active);
                uint8_t saved[SECTOR_BYTES];
                memcpy(saved, flash.sectors[active], sizeof saved);
                flash.fault = fault;
                flash.cut = cut;
                io = journal_io(&flash);
                CHECK(rescue_journal_commit(&io, &current, &next) ==
                      RESCUE_JOURNAL_IO_ERROR);
                CHECK(memcmp(saved, flash.sectors[active], sizeof saved) == 0);
                if (fault == READ)
                    CHECK(flash.marker_written == (cut > reads - HEAD_READS));
                else
                    CHECK(flash.marker_written == (fault == MARKER && cut == 8));
                flash.fault = NONE;
                expect_head(&io, flash.marker_written ? &next : &current);
                ++cases;
            }
        }

        for (unsigned committed = 0; committed <= 1; ++committed) {
            const size_t start = committed ?
                reads - HEAD_READS + successful.target * READS_PER_VALID_SECTOR :
                HEAD_READS;
            for (size_t read = 1; read <= READS_PER_VALID_SECTOR; ++read) {
                struct flash flash = fixture(active);
                flash.fault = BAD_READ;
                flash.cut = start + read;
                io = journal_io(&flash);
                CHECK(rescue_journal_commit(&io, &current, &next) ==
                      RESCUE_JOURNAL_VERIFY_ERROR);
                CHECK(flash.mutations == 2 + committed);
                CHECK(flash.marker_written == (committed != 0));
                flash.fault = NONE;
                expect_head(&io, committed ? &next : &current);
            }
        }
    }
    return cases;
}

static void reject(struct flash *flash, const struct rescue_journal_record *expected,
                   const struct rescue_journal_record *next,
                   enum rescue_journal_result result)
{
    struct rescue_journal_io io = journal_io(flash);
    uint8_t saved[sizeof flash->sectors];
    memcpy(saved, flash->sectors, sizeof saved);
    CHECK(rescue_journal_commit(&io, expected, next) == result);
    CHECK(flash->mutations == 0);
    CHECK(memcmp(saved, flash->sectors, sizeof saved) == 0);
}

static void test_selection(void)
{
    const struct rescue_journal_record older = record(40);
    const struct rescue_journal_record current = record(41);
    const struct rescue_journal_record next = record(42);
    const struct rescue_journal_record maximum = record(UINT64_MAX);
    const struct rescue_journal_record wrapped = record(0);
    struct rescue_journal_record different = current;
    struct flash flash = fixture(0);
    struct rescue_journal_io io = journal_io(&flash);

    strcpy(different.reason, "different");
    reject(&flash, &older, &next, RESCUE_JOURNAL_STALE);
    reject(&flash, &different, &next, RESCUE_JOURNAL_STALE);
    reject(&flash, &current, &older, RESCUE_JOURNAL_INVALID);

    seed(&flash, 1, &different);
    struct rescue_journal_record output = older;
    CHECK(rescue_journal_read(&io, &output) == RESCUE_JOURNAL_AMBIGUOUS);
    CHECK(output.sequence == older.sequence && strcmp(output.reason, older.reason) == 0);
    reject(&flash, &current, &next, RESCUE_JOURNAL_AMBIGUOUS);

    seed(&flash, 0, &older);
    seed(&flash, 1, &next);
    CHECK(rescue_journal_read(&io, &output) == RESCUE_JOURNAL_AMBIGUOUS);

    for (size_t i = 0; i < SECTOR_BYTES; ++i) {
        flash = fixture(0);
        flash.sectors[0][i] ^= 1u;
        expect_head(&io, &older);
    }

    memset(flash.sectors, 0xff, sizeof flash.sectors);
    CHECK(rescue_journal_read(&io, &output) == RESCUE_JOURNAL_NO_RECORD);
    reject(&flash, &current, &next, RESCUE_JOURNAL_NO_RECORD);

    const struct rescue_journal_record before_maximum = record(UINT64_MAX - 1);
    seed(&flash, 0, &before_maximum);
    CHECK(rescue_journal_commit(&io, &before_maximum, &maximum) == RESCUE_JOURNAL_OK);
    expect_head(&io, &maximum);
    flash.mutations = 0;
    reject(&flash, &maximum, &wrapped, RESCUE_JOURNAL_OVERFLOW);
}

static void test_states(void)
{
    static const struct {
        enum rescue_record_state state;
        enum rescue_journal_state policy;
    } states[] = {
        { RESCUE_RECORD_STABLE, RESCUE_JOURNAL_STABLE },
        { RESCUE_RECORD_TRIAL_PENDING, RESCUE_JOURNAL_TRIAL_PENDING },
        { RESCUE_RECORD_TRIAL_RUNNING, RESCUE_JOURNAL_TRIAL_RUNNING },
        { RESCUE_RECORD_ROLLBACK_REQUIRED, RESCUE_JOURNAL_ROLLBACK_REQUIRED },
        { RESCUE_RECORD_RECOVERY_ONLY, RESCUE_JOURNAL_RECOVERY_ONLY }
    };
    const struct rescue_journal_record older = record(40);

    for (size_t i = 0; i < sizeof states / sizeof states[0]; ++i) {
        struct rescue_journal_record value = record(41);
        struct flash flash = fixture(0);
        struct rescue_journal_io io = journal_io(&flash);
        CHECK((int)states[i].state != (int)states[i].policy);
        value.state = states[i].state;
        if (value.state == RESCUE_RECORD_TRIAL_PENDING ||
            value.state == RESCUE_RECORD_TRIAL_RUNNING)
            value.pending.slot = RESCUE_JOURNAL_B;
        value.attempts = value.state == RESCUE_RECORD_TRIAL_PENDING;
        seed(&flash, 0, &value);
        CHECK(flash.sectors[0][112] == i);
        expect_head(&io, &value);

        value.state = (uint8_t)states[i].policy;
        uint8_t frame[RESCUE_JOURNAL_RECORD_BYTES];
        CHECK(rescue_journal_encode(&value, frame) == RESCUE_JOURNAL_INVALID);
        flash.sectors[0][112] = UINT8_MAX;
        expect_head(&io, &older);
    }
}

int main(void)
{
    test_states();
    test_selection();
    const unsigned cuts = test_faults();
    printf("PASS: %u interruption and read-error cases, 16 readback mismatches, "
           "%u single-byte corruption cases, state mapping and selection checks\n",
           cuts, (unsigned)SECTOR_BYTES);
    return EXIT_SUCCESS;
}
