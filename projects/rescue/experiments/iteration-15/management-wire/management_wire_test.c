#include "management_wire.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(condition) do {                                           \
    if (!(condition)) {                                                  \
        fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition);   \
        exit(EXIT_FAILURE);                                              \
    }                                                                    \
} while (0)

static const uint8_t begin[] = {
    1, 1, 0, 13, 0x12, 0x34, 0x56, 0x78,
    0x89, 0xab, 0xcd, 0xef, 0x10, 0x20, 0x30, 0x40, 0, 3, 0xa1, 0, 0xff
};
static const uint8_t chunk[] = {
    1, 2, 0, 13, 0x12, 0x34, 0x56, 0x78,
    0x89, 0xab, 0xcd, 0xef, 0, 1, 0x23, 0x45, 0, 3, 0x5a, 0xff, 0
};
static const uint8_t seal[] = {
    1, 3, 0, 4, 0x12, 0x34, 0x56, 0x78, 0x89, 0xab, 0xcd, 0xef
};
static const uint8_t cancel[] = {
    1, 4, 0, 4, 0x12, 0x34, 0x56, 0x78, 0x89, 0xab, 0xcd, 0xef
};
static const uint8_t status[] = { 1, 5, 0, 0, 0x12, 0x34, 0x56, 0x78 };

static struct fixture {
    unsigned calls;
    enum mw_operation operation;
    enum mw_code code;
    struct mw_progress progress;
} fixture;

static enum mw_code record(void *context, enum mw_operation operation,
                           struct mw_progress *progress)
{
    CHECK(context == &fixture);
    CHECK(fixture.operation == operation);
    CHECK(progress->state == MW_STATE_UNSPECIFIED);
    CHECK(progress->has_next_offset == 0);
    CHECK(progress->next_offset == 0);
    ++fixture.calls;
    *progress = fixture.progress;
    return fixture.code;
}

static enum mw_code on_begin(void *context, uint32_t id, uint32_t sequence,
                             const uint8_t *data, size_t size,
                             struct mw_progress *progress)
{
    CHECK(id == UINT32_C(0x89abcdef));
    CHECK(sequence == UINT32_C(0x10203040));
    CHECK(size == 3 && data == begin + 18);
    CHECK(memcmp(data, "\xa1\x00\xff", size) == 0);
    return record(context, MW_BEGIN, progress);
}

static enum mw_code on_chunk(void *context, uint32_t id, uint32_t offset,
                             const uint8_t *data, size_t size,
                             struct mw_progress *progress)
{
    CHECK(id == UINT32_C(0x89abcdef));
    CHECK(offset == UINT32_C(0x00012345));
    CHECK(size == 3 && data == chunk + 18);
    CHECK(memcmp(data, "\x5a\xff\x00", size) == 0);
    return record(context, MW_CHUNK, progress);
}

static enum mw_code on_seal(void *context, uint32_t id,
                            struct mw_progress *progress)
{
    CHECK(id == UINT32_C(0x89abcdef));
    return record(context, MW_SEAL, progress);
}

static enum mw_code on_cancel(void *context, uint32_t id,
                              struct mw_progress *progress)
{
    CHECK(id == UINT32_C(0x89abcdef));
    return record(context, MW_CANCEL, progress);
}

static enum mw_code on_status(void *context, struct mw_progress *progress)
{
    return record(context, MW_STATUS, progress);
}

static const struct mw_callbacks callbacks = {
    .begin = on_begin,
    .chunk = on_chunk,
    .seal = on_seal,
    .cancel = on_cancel,
    .status = on_status
};

static void expect_response(const uint8_t *request, size_t size,
                            const uint8_t expected[16], unsigned call_delta)
{
    uint8_t response[18];
    unsigned before = fixture.calls;

    memset(response, 0xa5, sizeof(response));
    CHECK(mw_decode(&callbacks, &fixture, request, size, response + 1, 16) == 16);
    CHECK(fixture.calls == before + call_delta);
    if (memcmp(response + 1, expected, 16) != 0) {
        fprintf(stderr, "response mismatch for operation %u, request size %zu\n",
                (unsigned)expected[1], size);
        for (size_t i = 0; i < 16; ++i)
            fprintf(stderr, "byte %zu: expected %02x, got %02x\n", i,
                    (unsigned)expected[i], (unsigned)response[i + 1]);
        exit(EXIT_FAILURE);
    }
    CHECK(response[0] == 0xa5 && response[17] == 0xa5);
}

static void expect_invalid(const uint8_t *request, size_t size, uint8_t code)
{
    uint8_t expected[16] = { 1, 0, 0, 8, 0, 0, 0, 0, 0, code };

    if (request && size >= 8) {
        expected[1] = request[1];
        memcpy(expected + 4, request + 4, 4);
    }
    expect_response(request, size, expected, 0);
}

static const struct operation_case {
    const uint8_t *request;
    size_t size;
    enum mw_operation operation;
    struct mw_progress progress;
    uint8_t response[16];
} cases[] = {
    { begin, sizeof(begin), MW_BEGIN, { MW_STATE_OPEN, 0, 1 },
      { 1, 1, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 0, 2, 1, 0, 0, 0, 0 } },
    { chunk, sizeof(chunk), MW_CHUNK, { MW_STATE_OPEN, 0x12348, 1 },
      { 1, 2, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 0, 2, 1, 0, 1, 0x23, 0x48 } },
    { seal, sizeof(seal), MW_SEAL, { MW_STATE_SEALED, 0, 0 },
      { 1, 3, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 0, 3, 0, 0, 0, 0, 0 } },
    { cancel, sizeof(cancel), MW_CANCEL, { MW_STATE_CANCELLED, 0, 0 },
      { 1, 4, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 0, 4, 0, 0, 0, 0, 0 } },
    { status, sizeof(status), MW_STATUS, { MW_STATE_IDLE, 0, 0 },
      { 1, 5, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 0, 1, 0, 0, 0, 0, 0 } }
};

static void test_operations_and_lengths(void)
{
    uint8_t frame[sizeof(begin) + 1];

    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        const struct operation_case *test = &cases[i];
        fixture.operation = test->operation;
        fixture.code = MW_OK;
        fixture.progress = test->progress;
        expect_response(test->request, test->size, test->response, 1);

        for (size_t prefix = 0; prefix < test->size; ++prefix) {
            memcpy(frame, test->request, prefix);
            expect_invalid(frame, prefix, 1);
            if (prefix >= 8) {
                frame[3] = (uint8_t)(prefix - 8);
                expect_invalid(frame, prefix, 1);
            }
        }

        memcpy(frame, test->request, test->size);
        frame[test->size] = 0;
        expect_invalid(frame, test->size + 1, 1);
        ++frame[3];
        expect_invalid(frame, test->size + 1, 1);
    }

    memcpy(frame, begin, sizeof(begin));
    frame[17] = 4;
    expect_invalid(frame, sizeof(begin), 1);
    frame[3] = 10;
    frame[17] = 0;
    expect_invalid(frame, 18, 1);

    memcpy(frame, chunk, sizeof(chunk));
    frame[17] = 2;
    expect_invalid(frame, sizeof(chunk), 1);
    frame[17] = 3;
    memset(frame + 12, 0xff, 4);
    expect_invalid(frame, sizeof(chunk), 1);
}

static void test_invalid_headers_and_limits(void)
{
    uint8_t frame[8 + 1201] = { 0 };

    expect_invalid(NULL, sizeof(status), 1);
    memcpy(frame, status, sizeof(status));
    frame[0] = 2;
    expect_invalid(frame, sizeof(status), 2);
    frame[0] = 1;
    frame[1] = 0xfe;
    expect_invalid(frame, sizeof(status), 3);
    frame[2] = 0x04;
    frame[3] = 0xb1;
    expect_invalid(frame, sizeof(frame), 4);

    frame[2] = 0x04;
    frame[3] = 0x0b;
    frame[16] = 0x04;
    frame[17] = 0x01;
    frame[1] = 1;
    expect_invalid(frame, 8 + 10 + 1025, 4);
    frame[1] = 2;
    expect_invalid(frame, 8 + 10 + 1025, 4);
}

static void test_progress(void)
{
    const uint8_t stale[16] = {
        1, 1, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 5, 1, 0, 0, 0, 0, 0
    };
    const uint8_t conflict[16] = {
        1, 2, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 5, 2, 1, 0, 1, 0x23, 0x44
    };
    const uint8_t open[16] = {
        1, 5, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 0, 2, 1, 0x89, 0xab, 0xcd, 0xef
    };
    const uint8_t missing[16] = {
        1, 5, 0, 8, 0x12, 0x34, 0x56, 0x78, 0, 6, 0, 0, 0, 0, 0, 0
    };

    fixture.operation = MW_BEGIN;
    fixture.code = MW_CONFLICT;
    fixture.progress = (struct mw_progress){ MW_STATE_IDLE, 0x1234, 0 };
    expect_response(begin, sizeof(begin), stale, 1);

    fixture.operation = MW_CHUNK;
    fixture.progress = (struct mw_progress){ MW_STATE_OPEN, 0x12344, 1 };
    expect_response(chunk, sizeof(chunk), conflict, 1);

    fixture.operation = MW_STATUS;
    fixture.code = MW_OK;
    fixture.progress = (struct mw_progress){ MW_STATE_OPEN, UINT32_C(0x89abcdef), 1 };
    expect_response(status, sizeof(status), open, 1);
    fixture.code = MW_NOT_FOUND;
    expect_response(status, sizeof(status), missing, 1);
}

static void test_response_capacity(void)
{
    uint8_t response[16];
    unsigned before = fixture.calls;

    memset(response, 0xa5, sizeof(response));
    for (size_t capacity = 0; capacity < sizeof(response); ++capacity) {
        CHECK(mw_decode(&callbacks, &fixture, status, sizeof(status),
                        response, capacity) == 0);
        CHECK(fixture.calls == before);
        for (size_t i = 0; i < sizeof(response); ++i)
            CHECK(response[i] == 0xa5);
    }
    CHECK(mw_decode(&callbacks, &fixture, status, sizeof(status),
                    NULL, sizeof(response)) == 0);
    CHECK(fixture.calls == before);
}

int main(void)
{
    test_operations_and_lengths();
    test_invalid_headers_and_limits();
    test_progress();
    test_response_capacity();
    puts("management wire tests passed");
    return EXIT_SUCCESS;
}
