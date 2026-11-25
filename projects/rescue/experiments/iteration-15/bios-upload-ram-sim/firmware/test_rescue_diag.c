#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "rescue_diag.h"

int main(void)
{
    static const char request[] = "RESCUE1 0123ABEF";
    static const char ok[] =
        "api_version=1\nrequest_id=0123ABEF\nmode=recovery-only\npaired=false\n"
        "identity_valid=false\njournal_valid=false\nflash_probe=ok\nwarning=LAB ONLY\n";
    static const char failed[] =
        "api_version=1\nrequest_id=0123ABEF\nmode=recovery-only\npaired=false\n"
        "identity_valid=false\njournal_valid=false\nflash_probe=failed\nwarning=LAB ONLY\n";
    static const char invalid[][17] = {
        "RESCUE2 0123ABEF", "RESCUE1 0123AbEF", "RESCUE1 0123ABE!",
        "RESCUE1 0123\nBEF", "RESCUE1\t0123ABEF", "RESCUE1 0123\0BEF",
    };
    char response[RESCUE_DIAG_MAX_RESPONSE + 1];

    memset(response, 'x', sizeof(response));
    assert(rescue_diag_handle(request, sizeof(request) - 1, RESCUE_FLASH_PROBE_OK,
                              response, sizeof(ok) - 1) == sizeof(ok) - 1);
    assert(memcmp(response, ok, sizeof(ok) - 1) == 0);
    assert(response[sizeof(ok) - 1] == 'x');

    for (int state = RESCUE_FLASH_PROBE_INVALID; state <= RESCUE_FLASH_PROBE_UNKNOWN_ID; ++state) {
        assert(rescue_diag_handle(request, sizeof(request) - 1, state, response,
                                  RESCUE_DIAG_MAX_RESPONSE) == sizeof(failed) - 1);
        assert(memcmp(response, failed, sizeof(failed) - 1) == 0);
    }

    memset(response, 'x', sizeof(response));
    for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); ++i)
        assert(!rescue_diag_handle(invalid[i], sizeof(request) - 1,
                                   RESCUE_FLASH_PROBE_OK, response, sizeof(response)));
    for (size_t size = 0; size < sizeof(request) - 1; ++size)
        assert(!rescue_diag_handle(request, size, RESCUE_FLASH_PROBE_OK,
                                   response, sizeof(response)));
    assert(!rescue_diag_handle(request, sizeof(request), RESCUE_FLASH_PROBE_OK,
                               response, sizeof(response)));
    assert(!rescue_diag_handle(request, sizeof(request) - 1, RESCUE_FLASH_PROBE_OK,
                               response, sizeof(ok) - 2));
    assert(!rescue_diag_handle(NULL, sizeof(request) - 1, RESCUE_FLASH_PROBE_OK,
                               response, sizeof(response)));
    assert(!rescue_diag_handle(request, sizeof(request) - 1, RESCUE_FLASH_PROBE_OK,
                               NULL, sizeof(response)));
    for (size_t i = 0; i < sizeof(response); ++i)
        assert(response[i] == 'x');

    puts("Rescue diagnostic request tests passed");
    return 0;
}
