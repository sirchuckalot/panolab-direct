#include "upload_session.h"
#include "build/fixtures.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

enum { EXPECTED_SEQUENCE = 23 };

struct fake_backend {
    enum pl_upload_begin_result begin_result;
    int append_error;
    int seal_error;
    int abort_error;
    unsigned begins, appends, seals, aborts;
    uint64_t id;
    size_t length;
    uint8_t data[sizeof(raw)];
};

static enum pl_upload_begin_result record_begin(
    void *context, uint64_t id, uint64_t sequence,
    const struct pl_manifest *parsed, const uint8_t *bytes, size_t length)
{
    struct fake_backend *fake = context;

    assert(sequence == EXPECTED_SEQUENCE);
    assert(length == sizeof(manifest));
    assert(memcmp(bytes, manifest, length) == 0);
    assert(parsed->image.image_length == sizeof(raw));
    assert(memcmp(parsed->manifest_sha256, digest, sizeof(digest)) == 0);
    ++fake->begins;
    fake->id = id;
    fake->length = 0;
    return fake->begin_result;
}

static int record_append(void *context, uint64_t id, uint64_t offset,
                         const uint8_t *bytes, size_t length)
{
    struct fake_backend *fake = context;

    assert(id == fake->id && offset == fake->length);
    assert(length > 0 && length <= PL_UPLOAD_MAX_CHUNK);
    assert(length <= sizeof(fake->data) - fake->length);
    memcpy(fake->data + fake->length, bytes, length);
    fake->length += length;
    ++fake->appends;
    return fake->append_error;
}

static int record_seal(void *context, uint64_t id)
{
    struct fake_backend *fake = context;

    assert(id == fake->id && fake->length == sizeof(raw));
    assert(memcmp(fake->data, raw, sizeof(raw)) == 0);
    ++fake->seals;
    return fake->seal_error;
}

static int record_abort(void *context, uint64_t id)
{
    struct fake_backend *fake = context;

    assert(id == fake->id);
    ++fake->aborts;
    if (fake->abort_error == 0)
        fake->length = 0;
    return fake->abort_error;
}

static const struct pl_upload_backend backend = {
    .begin = record_begin,
    .append = record_append,
    .seal = record_seal,
    .abort = record_abort,
};

static enum pl_upload_result begin(struct pl_upload_session *session, uint64_t id)
{
    return pl_upload_begin(session, id, EXPECTED_SEQUENCE, manifest, sizeof(manifest));
}

static void test_success_and_replay(void)
{
    struct fake_backend fake = {0};
    struct pl_upload_session session;

    assert(pl_upload_init(&session, &backend, &fake, sizeof(raw), 5) == PL_UPLOAD_OK);
    assert(begin(&session, 0) == PL_UPLOAD_STALE);
    assert(begin(&session, 5) == PL_UPLOAD_STALE);
    assert(begin(&session, 9) == PL_UPLOAD_OK);
    assert(begin(&session, 9) == PL_UPLOAD_STALE);
    assert(begin(&session, 10) == PL_UPLOAD_BUSY);
    assert(pl_upload_append(&session, 8, 0, raw, 1) == PL_UPLOAD_STALE);
    assert(pl_upload_cancel(&session, 8) == PL_UPLOAD_STALE);
    assert(pl_upload_append(&session, 9, 1, raw, 1) == PL_UPLOAD_OFFSET);
    assert(pl_upload_append(&session, 9, 0, raw, 200) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 9, 0, raw, 200) == PL_UPLOAD_OFFSET);
    assert(pl_upload_append(&session, 9, 199, raw + 199, 1) == PL_UPLOAD_OFFSET);
    assert(pl_upload_append(&session, 9, 201, raw + 201, 1) == PL_UPLOAD_OFFSET);
    assert(pl_upload_append(&session, 9, 200, raw + 200, sizeof(raw) - 200) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, 9) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, 9) == PL_UPLOAD_STALE);
    assert(pl_upload_append(&session, 9, 0, raw, 1) == PL_UPLOAD_STALE);
    assert(begin(&session, 8) == PL_UPLOAD_STALE);
    assert(begin(&session, 9) == PL_UPLOAD_STALE);
    assert(fake.begins == 1 && fake.appends == 2 && fake.seals == 1 && fake.aborts == 0);

    assert(begin(&session, 10) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 10, 0, raw, 1) == PL_UPLOAD_OK);
    assert(pl_upload_cancel(&session, 10) == PL_UPLOAD_OK);
    assert(pl_upload_cancel(&session, 10) == PL_UPLOAD_STALE);
    assert(begin(&session, 10) == PL_UPLOAD_STALE);
    assert(fake.aborts == 1 && fake.length == 0);
    assert(begin(&session, UINT64_MAX) == PL_UPLOAD_OK);
    assert(pl_upload_cancel(&session, UINT64_MAX) == PL_UPLOAD_OK);
    assert(begin(&session, UINT64_MAX) == PL_UPLOAD_STALE);
    assert(begin(&session, 1) == PL_UPLOAD_STALE);
    assert(fake.begins == 3 && fake.aborts == 2);
}

static void test_validation(void)
{
    const uint8_t oversized[PL_UPLOAD_MAX_CHUNK + 1] = {0};
    struct fake_backend fake = {0};
    struct pl_upload_session session;

    assert(pl_upload_init(&session, &backend, &fake, sizeof(raw) - 1, 0) == PL_UPLOAD_OK);
    assert(begin(&session, 1) == PL_UPLOAD_LENGTH);
    assert(pl_upload_init(&session, &backend, &fake, sizeof(raw), 1) == PL_UPLOAD_OK);
    assert(pl_upload_begin(&session, 2, EXPECTED_SEQUENCE,
                           manifest, sizeof(manifest) - 1) == PL_UPLOAD_MANIFEST);
    assert(begin(&session, 2) == PL_UPLOAD_STALE);
    assert(fake.begins == 0 && fake.aborts == 0);

    assert(begin(&session, 3) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 3, 0, oversized, sizeof(oversized)) == PL_UPLOAD_LENGTH);
    assert(pl_upload_append(&session, 3, 0, raw, 1) == PL_UPLOAD_STALE);
    assert(begin(&session, 4) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 4, 0, raw, 0) == PL_UPLOAD_LENGTH);
    assert(begin(&session, 5) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 5, 0, raw, 1) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 5, 1, raw, sizeof(raw)) == PL_UPLOAD_LENGTH);
    assert(begin(&session, 6) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, 6) == PL_UPLOAD_LENGTH);
    assert(begin(&session, 7) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 7, 0, old_raw, sizeof(old_raw)) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, 7) == PL_UPLOAD_DIGEST);
    assert(pl_upload_seal(&session, 7) == PL_UPLOAD_STALE);
    assert(fake.aborts == 5 && fake.appends == 2 && fake.seals == 0 && fake.length == 0);
}

static void test_backend_failures(void)
{
    struct fake_backend fake = {.begin_result = PL_UPLOAD_BEGIN_REJECTED};
    struct pl_upload_session session;

    assert(pl_upload_init(&session, &backend, &fake, sizeof(raw), 0) == PL_UPLOAD_OK);
    assert(begin(&session, 1) == PL_UPLOAD_REJECTED);
    assert(begin(&session, 1) == PL_UPLOAD_STALE);
    assert(fake.aborts == 0);

    fake.begin_result = PL_UPLOAD_BEGIN_ERROR;
    assert(begin(&session, 2) == PL_UPLOAD_BACKEND_ERROR);
    assert(begin(&session, 2) == PL_UPLOAD_STALE);
    assert(fake.aborts == 1);

    fake.begin_result = PL_UPLOAD_BEGIN_OK;
    fake.append_error = -1;
    assert(begin(&session, 3) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 3, 0, raw, 1) == PL_UPLOAD_BACKEND_ERROR);
    assert(fake.aborts == 2 && fake.length == 0);

    fake.append_error = 0;
    fake.seal_error = -1;
    assert(begin(&session, 4) == PL_UPLOAD_OK);
    assert(pl_upload_append(&session, 4, 0, raw, sizeof(raw)) == PL_UPLOAD_OK);
    assert(pl_upload_seal(&session, 4) == PL_UPLOAD_BACKEND_ERROR);
    assert(fake.seals == 1 && fake.aborts == 3 && fake.length == 0);

    fake.abort_error = -1;
    assert(begin(&session, 5) == PL_UPLOAD_OK);
    assert(pl_upload_cancel(&session, 5) == PL_UPLOAD_LOCKED);
    assert(begin(&session, 6) == PL_UPLOAD_LOCKED);
    assert(pl_upload_append(&session, 5, 0, raw, 1) == PL_UPLOAD_LOCKED);
    assert(pl_upload_seal(&session, 5) == PL_UPLOAD_LOCKED);
    assert(pl_upload_cancel(&session, 5) == PL_UPLOAD_LOCKED);
    assert(fake.begins == 5 && fake.appends == 2 && fake.seals == 1 && fake.aborts == 4);
}

int main(void)
{
    test_success_and_replay();
    test_validation();
    test_backend_failures();
    puts("upload session tests passed");
    return 0;
}
