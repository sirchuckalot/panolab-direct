#ifndef RESCUE_DIAG_H
#define RESCUE_DIAG_H

#include <stddef.h>

#include "rescue_flash_probe.h"

#define RESCUE_DIAG_PORT 49152u
#define RESCUE_DIAG_API_VERSION 1u
#define RESCUE_DIAG_MAX_RESPONSE 160u

/* Request is exactly "RESCUE1 " followed by eight uppercase hex digits.
 * Returns the response byte count (no NUL), or zero without writing. */
size_t rescue_diag_handle(const void *request, size_t length,
                          enum rescue_flash_probe_result probe,
                          void *response, size_t capacity);

#endif
