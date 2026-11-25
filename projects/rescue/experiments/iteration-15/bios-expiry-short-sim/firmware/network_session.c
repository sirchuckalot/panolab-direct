#include "network_session.h"

static void copy_bytes(uint8_t *to, const uint8_t *from, size_t size)
{
    for (size_t i = 0; i < size; ++i)
        to[i] = from[i];
}

static int equal_bytes(const uint8_t *a, const uint8_t *b, size_t size)
{
    for (size_t i = 0; i < size; ++i)
        if (a[i] != b[i])
            return 0;
    return 1;
}

static int same_peer(const struct ns_peer *a, const struct ns_peer *b)
{
    return a->port == b->port && equal_bytes(a->ip, b->ip, sizeof a->ip) &&
           equal_bytes(a->mac, b->mac, sizeof a->mac);
}

int ns_init(struct ns_session *s, const struct mw_callbacks *dispatch,
            ns_clock_fn clock, ns_reply_fn reply, void *context,
            uint64_t timeout_ms)
{
    if (!s || !dispatch || !clock || !reply || !timeout_ms)
        return 0;
    s->dispatch = *dispatch;
    s->clock = clock;
    s->reply = reply;
    s->context = context;
    s->timeout_ms = timeout_ms;
    s->queued = s->ticking = s->time_seen = s->owned = s->locked = 0;
    s->latest_valid = s->seal_valid = s->terminal = 0;
    return 1;
}

int ns_receive(struct ns_session *s, const struct ns_peer *peer,
               const uint8_t *bytes, size_t size)
{
    if (!s || !s->clock || s->queued || !peer || (!bytes && size) || size > NS_MAX_DATAGRAM)
        return 0;
    s->pending.peer = *peer;
    s->pending.size = size;
    copy_bytes(s->pending.bytes, bytes, size);
    s->queued = 1;
    return 1;
}

static void respond_code(const struct ns_datagram *d, enum mw_code code,
                         uint8_t *response)
{
    /* The decoder supplies the response header and zeroed progress. */
    mw_decode(NULL, NULL, d->bytes, d->size, response, MW_RESPONSE_SIZE);
    response[9] = (uint8_t)code;
}

static int same_id(const struct ns_datagram *d, const uint8_t *request)
{
    return equal_bytes(d->bytes + 4, request + 4, 4);
}

static void replay(const struct ns_datagram *d, const uint8_t *request,
                   size_t size, const uint8_t *saved, uint8_t *response)
{
    if (d->size == size && equal_bytes(d->bytes, request, size))
        copy_bytes(response, saved, MW_RESPONSE_SIZE);
    else
        respond_code(d, MW_CONFLICT, response);
}

static void handle(struct ns_session *s, uint64_t now, uint8_t *response)
{
    const struct ns_datagram *d = &s->pending;
    uint8_t op;

    if (s->locked || (s->owned && !same_peer(&s->owner, &d->peer))) {
        respond_code(d, s->locked ? MW_INTERNAL : MW_REJECTED, response);
        return;
    }
    if (d->size < MW_HEADER_SIZE) {
        mw_decode(NULL, NULL, d->bytes, d->size, response, MW_RESPONSE_SIZE);
        return;
    }
    if (s->seal_valid && same_peer(&s->seal_peer, &d->peer) &&
        same_id(d, s->seal_request)) {
        replay(d, s->seal_request, sizeof s->seal_request, s->seal_response,
               response);
        return;
    }
    if (s->latest_valid && same_peer(&s->latest.peer, &d->peer) &&
        same_id(d, s->latest.bytes)) {
        replay(d, s->latest.bytes, s->latest.size, s->latest_response, response);
        return;
    }

    op = d->bytes[1];
    if ((!s->owned && op >= MW_CHUNK && op <= MW_CANCEL) ||
        (!s->owned && op == MW_STATUS && (!s->terminal || !same_peer(&s->owner, &d->peer))) ||
        (s->owned && op == MW_BEGIN)) {
        respond_code(d, MW_REJECTED, response);
        return;
    }
    if (s->owned && op >= MW_CHUNK && op <= MW_CANCEL && d->size >= MW_HEADER_SIZE+4u) {
        const uint8_t *id=d->bytes+MW_HEADER_SIZE;
        uint32_t value=(uint32_t)id[0]<<24 | (uint32_t)id[1]<<16 | (uint32_t)id[2]<<8 | id[3];
        if(value!=s->operation_id){respond_code(d,MW_REJECTED,response);return;}
    }
    mw_decode(&s->dispatch, s->context, d->bytes, d->size, response,
              MW_RESPONSE_SIZE);
    if (response[9] == MW_INTERNAL && op >= MW_BEGIN && op <= MW_CANCEL)
        s->locked = 1;
    /* Foreign failed begins must not evict the terminal owner replay. */
    if (!s->owned && op == MW_BEGIN && response[9] != MW_OK && s->terminal) return;
    s->latest.peer = d->peer;
    s->latest.size = d->size;
    copy_bytes(s->latest.bytes, d->bytes, d->size);
    copy_bytes(s->latest_response, response, MW_RESPONSE_SIZE);
    s->latest_valid = 1;

    if (response[9] != MW_OK)
        return;

    s->last_success = now;
    if (op == MW_BEGIN) {
        const uint8_t *id = d->bytes + MW_HEADER_SIZE;
        s->operation_id = (uint32_t)id[0] << 24 | (uint32_t)id[1] << 16 |
                          (uint32_t)id[2] << 8 | (uint32_t)id[3];
        s->seal_valid = s->terminal = 0;
        s->owner = d->peer;
        s->owned = 1;
    } else if (op == MW_CANCEL || op == MW_SEAL) {
        s->owned = 0;
        s->terminal = 1;
        if (op == MW_SEAL) {
            s->seal_peer = d->peer;
            copy_bytes(s->seal_request, d->bytes, sizeof s->seal_request);
            copy_bytes(s->seal_response, response, MW_RESPONSE_SIZE);
            s->seal_valid = 1;
        }
    }
}

void ns_tick(struct ns_session *s)
{
    uint64_t now;
    uint8_t response[MW_RESPONSE_SIZE];

    if (!s || !s->clock || s->ticking)
        return;
    s->ticking = 1;
    now = s->clock(s->context);
    if (s->time_seen && now < s->last_now)
        s->locked = 1;
    s->time_seen = 1;
    s->last_now = now;

    if (!s->locked && s->owned && now - s->last_success >= s->timeout_ms) {
        struct mw_progress progress = { MW_STATE_UNSPECIFIED, 0, 0 };

        s->latest_valid = 0;
        if (s->dispatch.cancel &&
            s->dispatch.cancel(s->context, s->operation_id, &progress) == MW_OK)
            s->owned = s->terminal = s->seal_valid = 0;
        else
            s->locked = 1;
    }

    if (s->queued) {
        handle(s, now, response);
        s->reply(s->context, &s->pending.peer, response, sizeof response);
        s->queued = 0;
    }
    s->ticking = 0;
}
