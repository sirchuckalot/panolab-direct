#include "rescue_flash_transaction.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CAPACITY = 16 * 1024 * 1024,
    SECTOR = 256 * 1024,
    PAGE = 256,
    IMAGE_LENGTH = SECTOR + 37,
    ERASES = (IMAGE_LENGTH + SECTOR - 1) / SECTOR,
    PROGRAMS = (IMAGE_LENGTH + PAGE - 1) / PAGE,
    SENTINEL = 0x5a,
    APP_A = 2 * SECTOR,
    APP_B = 5 * SECTOR,
    STATE_0 = 9 * SECTOR,
    STATE_1 = 10 * SECTOR
};

static const struct rescue_region regions[] = {
    { RESCUE_REGION_BOOT, 0, SECTOR },
    { RESCUE_REGION_RESCUE, SECTOR, SECTOR },
    { RESCUE_REGION_APP_A, APP_A, 3 * SECTOR },
    { RESCUE_REGION_APP_B, APP_B, 3 * SECTOR },
    { RESCUE_REGION_IDENTITY, 8 * SECTOR, SECTOR },
    { RESCUE_REGION_STATE_0, STATE_0, SECTOR },
    { RESCUE_REGION_STATE_1, STATE_1, SECTOR },
    { RESCUE_REGION_RESERVED, CAPACITY - SECTOR, SECTOR }
};

static uint8_t nor[CAPACITY];
static uint8_t original[CAPACITY];
static uint8_t image[IMAGE_LENGTH];
static struct rescue_flash_geometry geometry;

struct simulator {
    uint32_t target;
    unsigned erases;
    unsigned programs;
    unsigned fail_at; /* One-based across erase and program callbacks. */
    bool partial_program;
    bool corrupt_program;
    bool fail_readback;
};

static int read_nor(void *context, uint32_t offset, uint8_t *data, size_t length)
{
    const struct simulator *sim = context;
    assert(offset <= CAPACITY && length <= CAPACITY - offset);
    if (offset >= sim->target && offset < sim->target + IMAGE_LENGTH) {
        assert(sim->programs == PROGRAMS);
        if (sim->fail_readback)
            return -1;
    }
    memcpy(data, nor + offset, length);
    return 0;
}

static int erase_nor(void *context, uint32_t offset)
{
    struct simulator *sim = context;
    assert(sim->erases < ERASES && sim->programs == 0);
    assert(offset == sim->target + sim->erases * SECTOR);
    if (++sim->erases == sim->fail_at)
        return -1;
    memset(nor + offset, 0xff, SECTOR);
    return 0;
}

static int program_nor(void *context, uint32_t offset,
                       const uint8_t *data, size_t length)
{
    struct simulator *sim = context;
    assert(sim->erases == ERASES && sim->programs < PROGRAMS);
    assert(offset == sim->target + sim->programs * PAGE && length == PAGE);
    for (size_t i = 0; i < length; ++i) {
        size_t index = offset - sim->target + i;
        assert(data[i] == (index < IMAGE_LENGTH ? image[index] : 0xff));
    }

    bool fail = sim->erases + ++sim->programs == sim->fail_at;
    if (fail && !sim->partial_program)
        return -1;
    if (fail)
        length /= 2;
    for (size_t i = 0; i < length; ++i) {
        assert((nor[offset + i] & data[i]) == data[i]);
        nor[offset + i] &= data[i];
    }
    if (sim->corrupt_program && sim->programs == PROGRAMS)
        nor[offset] &= 0xfe; /* A silently cleared bit in the final page. */
    return fail ? -1 : 0;
}

static size_t read_image(void *context, uint64_t offset, uint8_t *data, size_t length)
{
    (void)context;
    assert(offset <= sizeof image && length <= sizeof image - offset);
    memcpy(data, image + offset, length);
    return length;
}

struct fixture {
    struct rescue_journal_record expected;
    struct pl_image_metadata metadata;
    struct pl_image_policy policy;
    struct rescue_flash_stage_request request;
};

static void init_fixture(struct fixture *f, enum rescue_slot target)
{
    f->expected = (struct rescue_journal_record){
        .sequence = 7, .confirmed = { RESCUE_JOURNAL_A, { 0x12 } },
        .state = RESCUE_RECORD_STABLE, .reason = "confirmed"
    };
    f->metadata = (struct pl_image_metadata){
        .profile = PL_TRUSTED_LAN, .manifest_version = 1,
        .role = PL_APPLICATION,
        .target = { PL_PANO_G2, PL_REV_B, PL_XC6SLX150_2_FGG484, 3 },
        .rescue_api_major = 1, .rescue_api_min_minor = 2,
        .format = PL_XILINX_SPARTAN6_SPI_V1,
        .required_features = PL_FEATURE_ICAP_RETURN_V1,
        .image_length = sizeof image
    };
    struct pl_sha256 sha;
    pl_sha256_init(&sha);
    assert(pl_sha256_update(&sha, image, sizeof image) == 0);
    pl_sha256_final(&sha, f->metadata.image_sha256);

    f->policy = (struct pl_image_policy){
        .profile = PL_TRUSTED_LAN, .detected_target = f->metadata.target,
        .rescue_api_major = 1, .rescue_api_minor = 2,
        .supported_features = PL_FEATURE_ICAP_RETURN_V1,
        .max_image_length = 3 * SECTOR
    };
    f->request = (struct rescue_flash_stage_request){
        .geometry = &geometry, .regions = regions,
        .region_count = sizeof regions / sizeof regions[0],
        .expected = &f->expected, .target = target,
        .metadata = &f->metadata, .policy = &f->policy,
        .raw_length = sizeof image, .read_image = read_image
    };
}

static void seed_flash(const struct rescue_journal_record *current)
{
    memset(original, SENTINEL, sizeof original);
    memset(original + STATE_0, 0xff, 2 * SECTOR);
    if (current) {
        assert(rescue_journal_encode(current, original + STATE_1) == RESCUE_JOURNAL_OK);
        if (current->sequence > 0) {
            struct rescue_journal_record older = *current;
            --older.sequence;
            assert(rescue_journal_encode(&older, original + STATE_0) == RESCUE_JOURNAL_OK);
        }
    }
}

static void expect_bytes(const uint8_t *bytes, size_t length, uint8_t value)
{
    for (size_t i = 0; i < length; ++i)
        assert(bytes[i] == value);
}

static void run_case(const struct fixture *f, struct simulator sim,
                     enum rescue_flash_result expected,
                     unsigned erases, unsigned programs)
{
    sim.target = f->request.target == RESCUE_SLOT_A ? APP_A : APP_B;
    const struct rescue_flash_io io = {
        .context = &sim, .read = read_nor, .erase = erase_nor, .program = program_nor
    };
    struct rescue_flash_verified verified;
    uint8_t saved[sizeof verified];

    memcpy(nor, original, sizeof nor);
    memset(&verified, 0xa5, sizeof verified);
    memcpy(saved, &verified, sizeof saved);
    enum rescue_flash_result actual = rescue_flash_stage(&io, &f->request, &verified);
    if (actual != expected || sim.erases != erases || sim.programs != programs)
        fprintf(stderr, "target %u, fault %u: got result/counts %d/%u/%u, expected %d/%u/%u\n",
                sim.target, sim.fail_at, actual, sim.erases, sim.programs,
                expected, erases, programs);
    assert(actual == expected);
    assert(sim.erases == erases && sim.programs == programs);

    size_t end = sim.target + ERASES * SECTOR;
    assert(memcmp(nor + STATE_0, original + STATE_0, 2 * SECTOR) == 0);
    assert(memcmp(nor, original, sim.target) == 0);
    assert(memcmp(nor + end, original + end, sizeof nor - end) == 0);

    if (expected != RESCUE_FLASH_OK)
        assert(memcmp(&verified, saved, sizeof verified) == 0);
    else {
        assert(verified.slot == f->request.target);
        assert(verified.image_length == sizeof image);
        assert(memcmp(verified.digest, f->metadata.image_sha256,
                      sizeof verified.digest) == 0);
    }

    if (erases == 0) {
        assert(memcmp(nor, original, sizeof nor) == 0);
        return;
    }

    unsigned erased = erases;
    if (sim.fail_at && sim.fail_at <= ERASES)
        --erased;
    unsigned written = programs;
    if (sim.fail_at > ERASES)
        --written;
    size_t image_written = written * PAGE;
    if (sim.partial_program)
        image_written += PAGE / 2;
    if (image_written > sizeof image)
        image_written = sizeof image;

    if (sim.corrupt_program) {
        size_t corrupt_offset = (PROGRAMS - 1) * PAGE;
        assert(memcmp(nor + sim.target, image, corrupt_offset) == 0);
        assert(nor[sim.target + corrupt_offset] == (image[corrupt_offset] & 0xfe));
        assert(nor[sim.target + corrupt_offset] != image[corrupt_offset]);
        assert(memcmp(nor + sim.target + corrupt_offset + 1,
                      image + corrupt_offset + 1, sizeof image - corrupt_offset - 1) == 0);
    } else {
        assert(memcmp(nor + sim.target, image, image_written) == 0);
    }
    expect_bytes(nor + sim.target + image_written,
                 erased * SECTOR - image_written, 0xff);
    expect_bytes(nor + sim.target + erased * SECTOR,
                 (ERASES - erased) * SECTOR, SENTINEL);
}

static void test_validation(void)
{
    struct fixture f;
    const struct simulator normal = {0};
    init_fixture(&f, RESCUE_SLOT_B);
    seed_flash(&f.expected);

    f.request.target = RESCUE_SLOT_NONE;
    run_case(&f, normal, RESCUE_FLASH_ARGUMENT, 0, 0);
    f.request.target = RESCUE_SLOT_B;
    ++f.metadata.target.bsp_version;
    run_case(&f, normal, RESCUE_FLASH_IMAGE, 0, 0);
    --f.metadata.target.bsp_version;
    ++f.metadata.manifest_version;
    run_case(&f, normal, RESCUE_FLASH_IMAGE, 0, 0);
    --f.metadata.manifest_version;
    f.metadata.image_sha256[0] ^= 1;
    run_case(&f, normal, RESCUE_FLASH_IMAGE, 0, 0);
    f.metadata.image_sha256[0] ^= 1;

    --f.expected.sequence;
    run_case(&f, normal, RESCUE_FLASH_STALE, 0, 0);
    ++f.expected.sequence;
    f.expected.confirmed.digest[0] ^= 1;
    run_case(&f, normal, RESCUE_FLASH_STALE, 0, 0);
    f.expected.confirmed.digest[0] ^= 1;

    f.request.active = RESCUE_SLOT_B;
    run_case(&f, normal, RESCUE_FLASH_PROTECTED, 0, 0);
    f.request.active = RESCUE_SLOT_NONE;
    f.request.target = RESCUE_SLOT_A;
    run_case(&f, normal, RESCUE_FLASH_PROTECTED, 0, 0);
    f.request.target = RESCUE_SLOT_B;
    f.expected.previous = (struct rescue_journal_binding){ RESCUE_JOURNAL_B, { 0x34 } };
    seed_flash(&f.expected);
    run_case(&f, normal, RESCUE_FLASH_PROTECTED, 0, 0);

    f.expected.pending = f.expected.previous;
    f.expected.previous = (struct rescue_journal_binding){0};
    f.expected.state = RESCUE_RECORD_TRIAL_PENDING;
    f.expected.attempts = 1;
    seed_flash(&f.expected);
    run_case(&f, normal, RESCUE_FLASH_JOURNAL, 0, 0);
}

static void test_first_update(void)
{
    struct fixture f;
    const struct simulator normal = {0};
    init_fixture(&f, RESCUE_SLOT_A);
    f.expected = (struct rescue_journal_record){
        .state = RESCUE_RECORD_RECOVERY_ONLY, .reason = "initialized"
    };
    seed_flash(NULL);
    run_case(&f, normal, RESCUE_FLASH_JOURNAL, 0, 0);
    seed_flash(&f.expected);
    run_case(&f, normal, RESCUE_FLASH_OK, ERASES, PROGRAMS);
}

static void test_write_and_readback(void)
{
    struct fixture f;
    init_fixture(&f, RESCUE_SLOT_B);
    seed_flash(&f.expected);
    run_case(&f, (struct simulator){0}, RESCUE_FLASH_OK, ERASES, PROGRAMS);

    for (unsigned i = 1; i <= ERASES; ++i)
        run_case(&f, (struct simulator){ .fail_at = i }, RESCUE_FLASH_IO, i, 0);
    for (unsigned i = 1; i <= PROGRAMS; ++i)
        run_case(&f, (struct simulator){ .fail_at = ERASES + i },
                 RESCUE_FLASH_IO, ERASES, i);

    run_case(&f, (struct simulator){ .fail_at = ERASES + 2, .partial_program = true },
             RESCUE_FLASH_IO, ERASES, 2);
    run_case(&f, (struct simulator){ .corrupt_program = true },
             RESCUE_FLASH_READBACK, ERASES, PROGRAMS);
    run_case(&f, (struct simulator){ .fail_readback = true },
             RESCUE_FLASH_READBACK, ERASES, PROGRAMS);
}

int main(void)
{
    assert(rescue_geometry_lookup(0x202018u, &geometry));
    assert(geometry.capacity == CAPACITY && geometry.erase_size == SECTOR &&
           geometry.page_size == PAGE);
    assert(rescue_layout_valid(&geometry, regions, sizeof regions / sizeof regions[0]));
    for (size_t i = 0; i < sizeof image; ++i)
        image[i] = (uint8_t)(i * 29u + i / PAGE + 1u);

    test_validation();
    test_first_update();
    test_write_and_readback();
    puts("flash transaction tests passed");
    return 0;
}
