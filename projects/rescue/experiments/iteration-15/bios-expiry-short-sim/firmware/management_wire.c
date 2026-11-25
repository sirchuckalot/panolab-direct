#include "management_wire.h"

static uint16_t read16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] << 8 | p[1]);
}

static uint32_t read32(const uint8_t *p)
{
    return (uint32_t)p[0] << 24 | (uint32_t)p[1] << 16 |
           (uint32_t)p[2] << 8 | (uint32_t)p[3];
}

static void write32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)value;
}

static enum mw_code dispatch(const struct mw_callbacks *cb, void *context,
                             uint8_t op, const uint8_t *body, size_t size,
                             struct mw_progress *progress)
{
    size_t length;

    switch (op) {
    case MW_BEGIN:
    case MW_CHUNK:
        if (size < 10u)
            return MW_MALFORMED;
        length = read16(body + 8);
        if (length == 0 || length != size - 10u)
            return MW_MALFORMED;
        if (length > (op == MW_BEGIN ? MW_MAX_MANIFEST : MW_MAX_CHUNK))
            return MW_TOO_LARGE;
        if (op == MW_BEGIN && cb && cb->begin)
            return cb->begin(context, read32(body), read32(body + 4),
                             body + 10, length, progress);
        if (op == MW_CHUNK) {
            uint32_t offset = read32(body + 4);
            if (length > UINT32_MAX - offset)
                return MW_MALFORMED;
            if (cb && cb->chunk)
                return cb->chunk(context, read32(body), offset,
                                 body + 10, length, progress);
        }
        return MW_INTERNAL;
    case MW_SEAL:
    case MW_CANCEL:
        if (size != 4u)
            return MW_MALFORMED;
        if (op == MW_SEAL && cb && cb->seal)
            return cb->seal(context, read32(body), progress);
        if (op == MW_CANCEL && cb && cb->cancel)
            return cb->cancel(context, read32(body), progress);
        return MW_INTERNAL;
    case MW_STATUS:
        if (size != 0)
            return MW_MALFORMED;
        return cb && cb->status ? cb->status(context, progress) : MW_INTERNAL;
    default:
        return MW_UNSUPPORTED_OPERATION;
    }
}

size_t mw_decode(const struct mw_callbacks *callbacks, void *context,
                 const uint8_t *request, size_t request_size,
                 uint8_t *response, size_t response_capacity)
{
    struct mw_progress progress = { MW_STATE_UNSPECIFIED, 0, 0 };
    enum mw_code code = MW_MALFORMED;
    uint32_t id = 0;
    uint8_t op = 0;
    size_t size;

    if (!response || response_capacity < MW_RESPONSE_SIZE)
        return 0;
    if (request && request_size >= MW_HEADER_SIZE) {
        size = request_size - MW_HEADER_SIZE;
        op = request[1];
        id = read32(request + 4);
        if (size > MW_MAX_PAYLOAD)
            code = MW_TOO_LARGE;
        else if (read16(request + 2) != size)
            code = MW_MALFORMED;
        else if (request[0] != MW_VERSION)
            code = MW_UNSUPPORTED_VERSION;
        else
            code = dispatch(callbacks, context, op, request + MW_HEADER_SIZE,
                            size, &progress);
    }

    if (code != MW_OK && code != MW_CONFLICT && code != MW_NOT_FOUND &&
        code != MW_REJECTED && code != MW_MALFORMED &&
        code != MW_UNSUPPORTED_VERSION && code != MW_UNSUPPORTED_OPERATION &&
        code != MW_TOO_LARGE)
        code = MW_INTERNAL;
    if (code != MW_OK && code != MW_CONFLICT)
        progress = (struct mw_progress){ MW_STATE_UNSPECIFIED, 0, 0 };
    if (progress.state < MW_STATE_UNSPECIFIED || progress.state > MW_STATE_CANCELLED)
        progress.state = MW_STATE_UNSPECIFIED;

    response[0] = MW_VERSION;
    response[1] = op;
    response[2] = 0;
    response[3] = MW_RESPONSE_SIZE - MW_HEADER_SIZE;
    write32(response + 4, id);
    response[8] = 0;
    response[9] = (uint8_t)code;
    response[10] = (uint8_t)progress.state;
    response[11] = progress.has_next_offset ? 1u : 0u;
    write32(response + 12, progress.has_next_offset ? progress.next_offset : 0);
    return MW_RESPONSE_SIZE;
}
