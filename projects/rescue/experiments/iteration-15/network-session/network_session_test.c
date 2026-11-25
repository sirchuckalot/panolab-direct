#include "network_session.h"

#include <assert.h>
#include <string.h>

#define OP_ID UINT32_C(0x12345678)

static const struct ns_peer owner = {{192, 0, 2, 1}, 5000, {2, 0, 0, 0, 0, 1}};
static const struct ns_peer other = {{192, 0, 2, 2}, 5000, {2, 0, 0, 0, 0, 1}};

struct fixture {
    struct ns_session session;
    uint64_t now;
    unsigned calls[MW_STATUS + 1];
    unsigned replies;
    enum mw_code result[MW_STATUS + 1];
    struct ns_peer recipient;
    uint8_t response[MW_RESPONSE_SIZE];
};

static enum mw_code record(struct fixture *f, enum mw_operation op,
                           struct mw_progress *p)
{
    ++f->calls[op];
    p->state = op == MW_SEAL ? MW_STATE_SEALED : MW_STATE_OPEN;
    p->next_offset = f->calls[op];
    p->has_next_offset = 1;
    return f->result[op];
}

static enum mw_code begin(void *ctx, uint32_t id, uint32_t sequence,
                          const uint8_t *data, size_t size, struct mw_progress *p)
{
    assert(id == OP_ID && sequence == 3 && size == 1 && data[0] == 0xa5);
    return record(ctx, MW_BEGIN, p);
}

static enum mw_code chunk(void *ctx, uint32_t id, uint32_t offset,
                          const uint8_t *data, size_t size, struct mw_progress *p)
{
    assert(id == OP_ID && offset == 3 && size == 1 && data[0] == 0xa5);
    return record(ctx, MW_CHUNK, p);
}

static enum mw_code seal(void *ctx, uint32_t id, struct mw_progress *p)
{
    assert(id == OP_ID);
    return record(ctx, MW_SEAL, p);
}

static enum mw_code cancel(void *ctx, uint32_t id, struct mw_progress *p)
{
    assert(id == OP_ID);
    return record(ctx, MW_CANCEL, p);
}

static enum mw_code status(void *ctx, struct mw_progress *p)
{
    return record(ctx, MW_STATUS, p);
}

static uint64_t clock_ms(void *ctx)
{
    return ((struct fixture *)ctx)->now;
}

static void reply(void *ctx, const struct ns_peer *peer,
                  const uint8_t *response, size_t size)
{
    struct fixture *f = ctx;

    assert(size == sizeof f->response);
    f->recipient = *peer;
    memcpy(f->response, response, size);
    ++f->replies;
}

static void init(struct fixture *f)
{
    const struct mw_callbacks callbacks = {begin, chunk, seal, cancel, status};

    *f = (struct fixture){0};
    assert(ns_init(&f->session, &callbacks, clock_ms, reply, f, 10));
}

static void put32(uint8_t *bytes, uint32_t value)
{
    bytes[0] = (uint8_t)(value >> 24);
    bytes[1] = (uint8_t)(value >> 16);
    bytes[2] = (uint8_t)(value >> 8);
    bytes[3] = (uint8_t)value;
}

static size_t packet(uint8_t *bytes, enum mw_operation op, uint32_t request_id,
                     uint32_t operation_id)
{
    uint8_t length = op <= MW_CHUNK ? 11 : (op == MW_STATUS ? 0 : 4);

    memset(bytes, 0, MW_HEADER_SIZE + length);
    bytes[0] = MW_VERSION;
    bytes[1] = (uint8_t)op;
    bytes[3] = length;
    put32(bytes + 4, request_id);
    if (length)
        put32(bytes + MW_HEADER_SIZE, operation_id);
    if (length == 11) {
        put32(bytes + MW_HEADER_SIZE + 4, 3);
        bytes[MW_HEADER_SIZE + 9] = 1;
        bytes[MW_HEADER_SIZE + 10] = 0xa5;
    }
    return MW_HEADER_SIZE + length;
}

static void expect_reply(const struct fixture *f, const struct ns_peer *peer,
                         enum mw_code code, unsigned replies)
{
    assert(f->replies == replies);
    assert(f->recipient.port == peer->port);
    assert(memcmp(f->recipient.ip, peer->ip, sizeof peer->ip) == 0);
    assert(memcmp(f->recipient.mac, peer->mac, sizeof peer->mac) == 0);
    assert(f->response[0] == MW_VERSION && f->response[3] == 8);
    assert(f->response[9] == code);
    if (code != MW_OK && code != MW_CONFLICT)
        for (size_t i = 10; i < sizeof f->response; ++i)
            assert(f->response[i] == 0);
}

static void send(struct fixture *f, const struct ns_peer *peer,
                 enum mw_operation op, uint32_t request_id,
                 uint32_t operation_id, enum mw_code code)
{
    uint8_t bytes[MW_HEADER_SIZE + 11u];
    size_t size = packet(bytes, op, request_id, operation_id);
    unsigned replies = f->replies;

    assert(ns_receive(&f->session, peer, bytes, size));
    assert(f->replies == replies);
    ns_tick(&f->session);
    expect_reply(f, peer, code, replies + 1);
    assert(f->response[1] == (uint8_t)op);
    assert(memcmp(f->response + 4, bytes + 4, 4) == 0);
}

static void bounded_queue(void)
{
    struct fixture f;
    struct ns_peer source = owner;
    uint8_t bytes[NS_MAX_DATAGRAM + 1u] = {0};
    size_t size = packet(bytes, MW_BEGIN, 1, OP_ID);

    init(&f);
    assert(!ns_receive(NULL, &owner, bytes, size));
    assert(!ns_receive(&f.session, &owner, bytes, sizeof bytes));
    assert(!ns_receive(&f.session, NULL, bytes, size));
    assert(!ns_receive(&f.session, &owner, NULL, size));
    assert(ns_receive(&f.session, &source, bytes, size));
    source = other;
    memset(bytes, 0, sizeof bytes);
    assert(!ns_receive(&f.session, &other, bytes, NS_MAX_DATAGRAM));
    assert(f.replies == 0 && f.calls[MW_BEGIN] == 0);
    ns_tick(&f.session);
    expect_reply(&f, &owner, MW_OK, 1);
    assert(f.calls[MW_BEGIN] == 1);
    ns_tick(&f.session);
    assert(f.replies == 1);
    assert(ns_receive(&f.session, &owner, bytes, NS_MAX_DATAGRAM));
    ns_tick(&f.session);
    expect_reply(&f, &owner, MW_MALFORMED, 2);
    assert(ns_receive(&f.session, &owner, NULL, 0));
    ns_tick(&f.session);
    expect_reply(&f, &owner, MW_MALFORMED, 3);
    assert(f.calls[MW_BEGIN] == 1);
}

static void replay_and_ownership(void)
{
    struct fixture f;
    struct ns_peer foreign;
    uint8_t saved[MW_RESPONSE_SIZE];

    init(&f);
    send(&f, &other, MW_STATUS, 1, 0, MW_REJECTED);
    send(&f, &owner, MW_BEGIN, 1, OP_ID, MW_OK);
    send(&f, &owner, MW_CHUNK, 2, OP_ID, MW_OK);
    memcpy(saved, f.response, sizeof saved);
    send(&f, &owner, MW_STATUS, 2, 0, MW_CONFLICT);
    send(&f, &other, MW_CHUNK, 2, OP_ID, MW_REJECTED);
    foreign = owner;
    ++foreign.port;
    send(&f, &foreign, MW_STATUS, 2, 0, MW_REJECTED);
    foreign = owner;
    ++foreign.mac[5];
    send(&f, &foreign, MW_STATUS, 3, 0, MW_REJECTED);
    send(&f, &owner, MW_CHUNK, 2, OP_ID, MW_OK);
    assert(memcmp(saved, f.response, sizeof saved) == 0);
    send(&f, &owner, MW_CHUNK, 3, OP_ID + 1, MW_REJECTED);
    send(&f, &owner, MW_SEAL, 4, OP_ID + 1, MW_REJECTED);
    send(&f, &owner, MW_CANCEL, 5, OP_ID + 1, MW_REJECTED);
    send(&f, &owner, MW_STATUS, 6, 0, MW_OK);
    assert(f.calls[MW_BEGIN] == 1 && f.calls[MW_CHUNK] == 1);
    assert(f.calls[MW_SEAL] == 0 && f.calls[MW_CANCEL] == 0);
    assert(f.calls[MW_STATUS] == 1);
}

static void expiry(void)
{
    struct fixture f;

    init(&f);
    send(&f, &owner, MW_BEGIN, 1, OP_ID, MW_OK);
    f.now = 4;
    send(&f, &owner, MW_CHUNK, 2, OP_ID, MW_OK);
    f.now = 13;
    send(&f, &owner, MW_CHUNK, 2, OP_ID, MW_OK);
    assert(f.calls[MW_CHUNK] == 1 && f.calls[MW_CANCEL] == 0);
    f.now = 14;
    ns_tick(&f.session);
    assert(f.calls[MW_CANCEL] == 1 && f.replies == 3);
    send(&f, &owner, MW_CHUNK, 2, OP_ID, MW_REJECTED);
    send(&f, &other, MW_STATUS, 5, 0, MW_REJECTED);
    ns_tick(&f.session);
    assert(f.calls[MW_CANCEL] == 1 && f.calls[MW_STATUS] == 0);
    send(&f, &other, MW_BEGIN, 1, OP_ID, MW_OK);
    assert(f.calls[MW_BEGIN] == 2);
}

static void terminal_replay(void)
{
    struct fixture f;
    uint8_t saved[MW_RESPONSE_SIZE];

    init(&f);
    send(&f, &owner, MW_BEGIN, 1, OP_ID, MW_OK);
    send(&f, &owner, MW_SEAL, 2, OP_ID, MW_OK);
    memcpy(saved, f.response, sizeof saved);
    send(&f, &owner, MW_SEAL, 2, OP_ID, MW_OK);
    assert(memcmp(saved, f.response, sizeof saved) == 0);
    f.now = 50;
    send(&f, &other, MW_SEAL, 2, OP_ID, MW_REJECTED);
    send(&f, &other, MW_STATUS, 2, 0, MW_REJECTED);
    send(&f, &owner, MW_SEAL, 2, OP_ID + 1, MW_CONFLICT);
    send(&f, &owner, MW_BEGIN, 3, OP_ID, MW_OK);
    send(&f, &owner, MW_CANCEL, 4, OP_ID, MW_OK);
    f.result[MW_BEGIN] = MW_REJECTED;
    send(&f, &other, MW_BEGIN, 4, OP_ID, MW_REJECTED);
    send(&f, &owner, MW_CANCEL, 4, OP_ID, MW_OK);
    send(&f, &owner, MW_SEAL, 2, OP_ID, MW_REJECTED);
    assert(f.calls[MW_BEGIN] == 3 && f.calls[MW_SEAL] == 1);
    assert(f.calls[MW_CANCEL] == 1 && f.calls[MW_STATUS] == 0);
}

static void lockout(void)
{
    struct fixture f;

    init(&f);
    f.now = 9;
    send(&f, &owner, MW_BEGIN, 1, OP_ID, MW_OK);
    f.now = 8;
    ns_tick(&f.session);
    f.now = 20;
    send(&f, &owner, MW_BEGIN, 1, OP_ID, MW_INTERNAL);
    send(&f, &other, MW_STATUS, 2, 0, MW_INTERNAL);
    assert(f.calls[MW_BEGIN] == 1 && f.calls[MW_CANCEL] == 0);
    assert(f.calls[MW_STATUS] == 0);

    init(&f);
    send(&f, &owner, MW_BEGIN, 1, OP_ID, MW_OK);
    f.result[MW_CANCEL] = MW_REJECTED;
    f.now = 10;
    send(&f, &other, MW_BEGIN, 2, OP_ID, MW_INTERNAL);
    ns_tick(&f.session);
    assert(f.calls[MW_CANCEL] == 1 && f.calls[MW_BEGIN] == 1);

    init(&f);
    send(&f, &owner, MW_BEGIN, 1, OP_ID, MW_OK);
    f.result[MW_CHUNK] = MW_INTERNAL;
    send(&f, &owner, MW_CHUNK, 2, OP_ID, MW_INTERNAL);
    send(&f, &owner, MW_CHUNK, 2, OP_ID, MW_INTERNAL);
    f.now = 20;
    send(&f, &owner, MW_CANCEL, 3, OP_ID, MW_INTERNAL);
    assert(f.calls[MW_CHUNK] == 1 && f.calls[MW_CANCEL] == 0);
}

int main(void)
{
    bounded_queue();
    replay_and_ownership();
    expiry();
    terminal_replay();
    lockout();
    return 0;
}
