#ifndef MANAGEMENT_WIRE_H
#define MANAGEMENT_WIRE_H

#include <stddef.h>
#include <stdint.h>

#define MW_VERSION 1u
#define MW_MAX_PAYLOAD 1200u
#define MW_MAX_MANIFEST 1024u
#define MW_MAX_CHUNK 1024u
#define MW_HEADER_SIZE 8u
#define MW_RESPONSE_SIZE 16u

enum mw_operation {
    MW_BEGIN = 1, MW_CHUNK = 2, MW_SEAL = 3, MW_CANCEL = 4, MW_STATUS = 5
};

enum mw_code {
    MW_OK = 0, MW_MALFORMED = 1, MW_UNSUPPORTED_VERSION = 2,
    MW_UNSUPPORTED_OPERATION = 3, MW_TOO_LARGE = 4, MW_CONFLICT = 5,
    MW_NOT_FOUND = 6, MW_REJECTED = 7, MW_INTERNAL = 8
};

enum mw_state {
    MW_STATE_UNSPECIFIED = 0, MW_STATE_IDLE = 1, MW_STATE_OPEN = 2,
    MW_STATE_SEALED = 3, MW_STATE_CANCELLED = 4
};

struct mw_progress {
    enum mw_state state;
    uint32_t next_offset;
    int has_next_offset;
};

struct mw_callbacks {
    enum mw_code (*begin)(void *, uint32_t id, uint32_t expected_sequence,
                          const uint8_t *manifest, size_t, struct mw_progress *);
    enum mw_code (*chunk)(void *, uint32_t id, uint32_t relative_offset,
                          const uint8_t *bytes, size_t, struct mw_progress *);
    enum mw_code (*seal)(void *, uint32_t id, struct mw_progress *);
    enum mw_code (*cancel)(void *, uint32_t id, struct mw_progress *);
    enum mw_code (*status)(void *, struct mw_progress *);
};

/* Returns bytes written, or zero if response is NULL or too small.
 * Request bytes passed to callbacks are borrowed for the duration of the call.
 * Request and response may overlap. See PROTOCOL.md for callback semantics.
 */
size_t mw_decode(const struct mw_callbacks *callbacks, void *context,
                 const uint8_t *request, size_t request_size,
                 uint8_t *response, size_t response_capacity);

#endif
