#ifndef PL_UPLOAD_SESSION_H
#define PL_UPLOAD_SESSION_H

#include "../manifest-core/manifest_core.h"

#define PL_UPLOAD_MAX_CHUNK 1024u

enum pl_upload_result {
    PL_UPLOAD_OK = 0,
    PL_UPLOAD_ARGUMENT,
    PL_UPLOAD_STALE,
    PL_UPLOAD_BUSY,
    PL_UPLOAD_MANIFEST,
    PL_UPLOAD_LENGTH,
    PL_UPLOAD_OFFSET,
    PL_UPLOAD_DIGEST,
    PL_UPLOAD_REJECTED,
    PL_UPLOAD_BACKEND_ERROR,
    PL_UPLOAD_LOCKED
};

enum pl_upload_begin_result {
    PL_UPLOAD_BEGIN_OK = 0,
    PL_UPLOAD_BEGIN_REJECTED,
    PL_UPLOAD_BEGIN_ERROR
};

/* Callbacks are synchronous and must not reenter the session. Pointer
 * arguments are borrowed only for the duration of the call.
 */
struct pl_upload_backend {
    /* Validate target compatibility and the expected journal sequence before
     * any mutation. REJECTED guarantees no mutation. ERROR may be ambiguous.
     */
    enum pl_upload_begin_result (*begin)(
        void *context, uint64_t id, uint64_t expected_sequence,
        const struct pl_manifest *manifest, const uint8_t *bytes, size_t length);
    int (*append)(void *context, uint64_t id, uint64_t offset,
                  const uint8_t *bytes, size_t length);
    int (*seal)(void *context, uint64_t id);
    /* Zero confirms invalidation of all artifacts for id, even if the
     * failed operation actually completed. A nonzero result locks the session.
     */
    int (*abort)(void *context, uint64_t id);
};

struct pl_upload_session {
    /* Internal state. Callers must serialize operations and use the API. */
    const struct pl_upload_backend *backend;
    void *context;
    uint64_t max_image_length;
    uint64_t last_id;
    uint64_t offset;
    struct pl_manifest manifest;
    struct pl_sha256 sha;
    uint8_t manifest_bytes[PL_MANIFEST_MAX_SIZE];
    unsigned active;
    unsigned locked;
};

/* Initialize fresh state after backend recovery, with the trusted server's
 * last consumed ID (zero if none). The backend table must remain stable.
 */
enum pl_upload_result pl_upload_init(struct pl_upload_session *session,
    const struct pl_upload_backend *backend, void *context,
    uint64_t max_image_length, uint64_t last_id);

/* A newer ID submitted while idle is consumed even if validation or the
 * backend fails. A busy session leaves newer IDs available for retry.
 */
enum pl_upload_result pl_upload_begin(struct pl_upload_session *session,
    uint64_t id, uint64_t expected_sequence, const uint8_t *manifest,
    size_t manifest_length);

/* An offset mismatch leaves the active upload available for retry at the
 * current offset. Invalid data at the current offset aborts the upload.
 */
enum pl_upload_result pl_upload_append(struct pl_upload_session *session,
    uint64_t id, uint64_t offset, const uint8_t *bytes, size_t length);
enum pl_upload_result pl_upload_seal(struct pl_upload_session *session, uint64_t id);
enum pl_upload_result pl_upload_cancel(struct pl_upload_session *session, uint64_t id);

#endif
