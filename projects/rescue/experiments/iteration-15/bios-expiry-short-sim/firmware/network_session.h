#ifndef NETWORK_SESSION_H
#define NETWORK_SESSION_H

#include "management_wire.h"

#define NS_MAX_DATAGRAM (MW_HEADER_SIZE + MW_MAX_PAYLOAD)

/* Simulation only. The IPv4 address, port and MAC are peer labels, not
 * authentication. State and replay protection are volatile across reset. */
struct ns_peer {
    uint8_t ip[4];
    uint16_t port;
    uint8_t mac[6];
};

typedef uint64_t (*ns_clock_fn)(void *context);
typedef void (*ns_reply_fn)(void *context, const struct ns_peer *peer,
                            const uint8_t *response, size_t size);

struct ns_datagram {
    struct ns_peer peer;
    size_t size;
    uint8_t bytes[NS_MAX_DATAGRAM];
};

struct ns_session {
    struct mw_callbacks dispatch;
    ns_clock_fn clock;
    ns_reply_fn reply;
    void *context;
    uint64_t timeout_ms, last_now, last_success;
    uint32_t operation_id;
    struct ns_peer owner;
    struct ns_datagram pending, latest;
    uint8_t latest_response[MW_RESPONSE_SIZE];
    struct ns_peer seal_peer;
    uint8_t seal_request[MW_HEADER_SIZE + 4u];
    uint8_t seal_response[MW_RESPONSE_SIZE];
    int queued, ticking, time_seen, owned, locked, latest_valid, seal_valid, terminal;
};

/* One cooperative caller. The callbacks share context. Timeout must be
 * positive. Peer and response pointers passed to reply are borrowed. */
int ns_init(struct ns_session *session, const struct mw_callbacks *dispatch,
            ns_clock_fn clock, ns_reply_fn reply, void *context,
            uint64_t timeout_ms);

/* Copies one datagram and its peer. Returns zero on drop. */
int ns_receive(struct ns_session *session, const struct ns_peer *peer,
               const uint8_t *bytes, size_t size);

/* Checks time even with an empty queue. Exact replays do not renew a lease.
 * One latest admitted request and one successful SEAL are retained. Older
 * correlation IDs are outside the replay window and must not be reused.
 * Successful CANCEL and SEAL end the active lease. Expiry clears the active
 * replay entry and requires a successful CANCEL before releasing ownership.
 * A locked instance rejects subsequent requests until reinitialized. */
void ns_tick(struct ns_session *session);

#endif
