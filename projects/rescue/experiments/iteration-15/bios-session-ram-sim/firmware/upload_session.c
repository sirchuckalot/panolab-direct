#include "upload_session.h"

#define SHA256_MAX_BYTES (UINT64_MAX / 8u)

enum pl_upload_result pl_upload_init(struct pl_upload_session *session,
    const struct pl_upload_backend *backend, void *context,
    uint64_t max_image_length, uint64_t last_id)
{
    if (session == NULL || backend == NULL || backend->begin == NULL ||
        backend->append == NULL || backend->seal == NULL || backend->abort == NULL ||
        max_image_length == 0 || max_image_length > SHA256_MAX_BYTES)
        return PL_UPLOAD_ARGUMENT;
    session->backend = backend;
    session->context = context;
    session->max_image_length = max_image_length;
    session->last_id = last_id;
    session->offset = 0;
    session->active = 0;
    session->locked = 0;
    return PL_UPLOAD_OK;
}

static enum pl_upload_result abort_session(struct pl_upload_session *session,
                                           enum pl_upload_result result)
{
    session->active = 0;
    if (session->backend->abort(session->context, session->last_id) != 0) {
        session->locked = 1;
        return PL_UPLOAD_LOCKED;
    }
    return result;
}

static enum pl_upload_result check_active(const struct pl_upload_session *session,
                                          uint64_t id)
{
    if (session == NULL)
        return PL_UPLOAD_ARGUMENT;
    if (session->locked)
        return PL_UPLOAD_LOCKED;
    if (!session->active || id != session->last_id)
        return PL_UPLOAD_STALE;
    return PL_UPLOAD_OK;
}

enum pl_upload_result pl_upload_begin(struct pl_upload_session *session,
    uint64_t id, uint64_t expected_sequence, const uint8_t *manifest,
    size_t manifest_length)
{
    enum pl_upload_begin_result result;

    if (session == NULL)
        return PL_UPLOAD_ARGUMENT;
    if (session->locked)
        return PL_UPLOAD_LOCKED;
    if (id <= session->last_id)
        return PL_UPLOAD_STALE;
    if (session->active)
        return PL_UPLOAD_BUSY;
    session->last_id = id;

    if (manifest == NULL || manifest_length == 0 ||
        manifest_length > sizeof(session->manifest_bytes))
        return PL_UPLOAD_MANIFEST;
    for (size_t i = 0; i < manifest_length; ++i)
        session->manifest_bytes[i] = manifest[i];
    if (pl_manifest_parse(session->manifest_bytes, manifest_length,
                          &session->manifest) != PL_MANIFEST_OK)
        return PL_UPLOAD_MANIFEST;
    if (session->manifest.image.image_length > session->max_image_length)
        return PL_UPLOAD_LENGTH;

    result = session->backend->begin(session->context, id, expected_sequence,
        &session->manifest, session->manifest_bytes, manifest_length);
    if (result == PL_UPLOAD_BEGIN_REJECTED)
        return PL_UPLOAD_REJECTED;
    if (result != PL_UPLOAD_BEGIN_OK)
        return abort_session(session, PL_UPLOAD_BACKEND_ERROR);

    pl_sha256_init(&session->sha);
    session->offset = 0;
    session->active = 1;
    return PL_UPLOAD_OK;
}

enum pl_upload_result pl_upload_append(struct pl_upload_session *session,
    uint64_t id, uint64_t offset, const uint8_t *bytes, size_t length)
{
    enum pl_upload_result result = check_active(session, id);

    if (result != PL_UPLOAD_OK)
        return result;
    if (offset != session->offset)
        return PL_UPLOAD_OFFSET;
    if (bytes == NULL)
        return abort_session(session, PL_UPLOAD_ARGUMENT);
    if (length == 0 || length > PL_UPLOAD_MAX_CHUNK ||
        length > session->manifest.image.image_length - session->offset)
        return abort_session(session, PL_UPLOAD_LENGTH);
    if (pl_sha256_update(&session->sha, bytes, length) != 0)
        return abort_session(session, PL_UPLOAD_LENGTH);
    if (session->backend->append(session->context, id, offset, bytes, length) != 0)
        return abort_session(session, PL_UPLOAD_BACKEND_ERROR);
    session->offset += length;
    return PL_UPLOAD_OK;
}

enum pl_upload_result pl_upload_seal(struct pl_upload_session *session, uint64_t id)
{
    enum pl_upload_result result = check_active(session, id);
    uint8_t digest[PL_SHA256_SIZE];
    unsigned difference = 0;

    if (result != PL_UPLOAD_OK)
        return result;
    if (session->offset != session->manifest.image.image_length)
        return abort_session(session, PL_UPLOAD_LENGTH);

    pl_sha256_final(&session->sha, digest);
    for (size_t i = 0; i < sizeof(digest); ++i)
        difference |= (unsigned)(digest[i] ^ session->manifest.image.image_sha256[i]);
    if (difference != 0)
        return abort_session(session, PL_UPLOAD_DIGEST);
    if (session->backend->seal(session->context, id) != 0)
        return abort_session(session, PL_UPLOAD_BACKEND_ERROR);
    session->active = 0;
    return PL_UPLOAD_OK;
}

enum pl_upload_result pl_upload_cancel(struct pl_upload_session *session, uint64_t id)
{
    enum pl_upload_result result = check_active(session, id);

    if (result != PL_UPLOAD_OK)
        return result;
    return abort_session(session, PL_UPLOAD_OK);
}
