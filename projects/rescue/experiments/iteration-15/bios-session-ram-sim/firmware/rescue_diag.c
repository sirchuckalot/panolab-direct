#include <string.h>

#include "rescue_diag.h"

#define REQUEST_PREFIX "RESCUE1 "
#define ID_LENGTH 8u

static const char reply_prefix[] = "api_version=1\nrequest_id=";
static const char reply_status[] =
    "\nmode=recovery-only\npaired=false\nidentity_valid=false\n"
    "journal_valid=false\nflash_probe=";
static const char reply_warning[] = "\nwarning=LAB ONLY\n";

size_t rescue_diag_handle(const void *request, size_t length,
                          enum rescue_flash_probe_result probe,
                          void *response, size_t capacity)
{
    const size_t prefix_length = sizeof(REQUEST_PREFIX) - 1;
    if (request == NULL || response == NULL || length != prefix_length + ID_LENGTH)
        return 0;

    const char *bytes = request;
    for (size_t i = 0; i < prefix_length; ++i) {
        if (bytes[i] != REQUEST_PREFIX[i])
            return 0;
    }

    const char *id = bytes + prefix_length;
    for (size_t i = 0; i < ID_LENGTH; ++i) {
        if (!((id[i] >= '0' && id[i] <= '9') || (id[i] >= 'A' && id[i] <= 'F')))
            return 0;
    }

    const char *state = probe == RESCUE_FLASH_PROBE_OK ? "ok" : "failed";
    const size_t state_length = strlen(state);
    const size_t reply_length = sizeof(reply_prefix) - 1 + ID_LENGTH +
        sizeof(reply_status) - 1 + state_length + sizeof(reply_warning) - 1;
    if (reply_length > capacity || reply_length > RESCUE_DIAG_MAX_RESPONSE)
        return 0;

    char *out = response;
    memcpy(out, reply_prefix, sizeof(reply_prefix) - 1);
    out += sizeof(reply_prefix) - 1;
    memcpy(out, id, ID_LENGTH);
    out += ID_LENGTH;
    memcpy(out, reply_status, sizeof(reply_status) - 1);
    out += sizeof(reply_status) - 1;
    memcpy(out, state, state_length);
    out += state_length;
    memcpy(out, reply_warning, sizeof(reply_warning) - 1);
    return reply_length;
}
