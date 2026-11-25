#include <stdio.h>

#include <generated/csr.h>
#include <generated/soc.h>

#include "rescue_bios.h"
#include "rescue_diag.h"
#include "rescue_boot_policy.h"
#include "rescue_flash_probe.h"
#include "rescue_spi_nor.h"
#include "rescue_protected_read.h"
static int persistent_read(void *ctx, uint32_t addr, uint8_t *data, size_t n)
{ return rescue_spi_nor_read(ctx, addr, data, n) == RESCUE_SPI_NOR_OK ? 0 : -1; }

#if !defined(CONFIG_BIOS_NO_BOOT) || defined(BIOS_CONSOLE_DISABLE)
#error "Rescue diagnostics require stock boot disabled and the console enabled"
#endif

#define RESCUE_TIMEOUT_MS (PANOLAB_AUTOBOOT_WINDOW_S * UINT32_C(1000))
_Static_assert(RESCUE_TIMEOUT_MS >= RESCUE_AUTOBOOT_MIN_MS &&
               RESCUE_TIMEOUT_MS <= RESCUE_AUTOBOOT_MAX_MS,
               "Rescue timeout outside policy domain");

#ifdef CSR_ETHMAC_BASE
#include <libliteeth/udp.h>
#include "readline.h"

_Static_assert(PANOLAB_RESCUE_API == RESCUE_DIAG_API_VERSION,
               "Generated API version differs from the diagnostic protocol");

static enum rescue_flash_probe_result startup_probe;

static void rescue_diag_receive(uint32_t src_ip, uint16_t src_port,
                                uint16_t dst_port, void *data, uint32_t length)
{
    if (dst_port != RESCUE_DIAG_PORT || src_port == 0 ||
        (src_ip >> 24) == 0 || (src_ip >> 24) >= 224)
        return;

    size_t response_length = rescue_diag_handle(data, length, startup_probe,
                                               udp_get_tx_buffer(),
                                               RESCUE_DIAG_MAX_RESPONSE);
    if (response_length)
        udp_reply(RESCUE_DIAG_PORT, src_port, response_length);
}
#endif

void rescue_bios_diagnose(void)
{
    struct rescue_boot_policy policy = {0};
    /* Verification and the policy's monotonic time source are unavailable. */
    struct rescue_boot_inputs inputs = {0};

    /* One volatile CSR read per poll. Bound the wait even if sampled is stuck. */
    for (uint32_t poll = 0; poll < PANOLAB_BUTTON_POLL_LIMIT; ++poll) {
        if (rescue_button_sampled_read()) {
            inputs.button_sampled = true;
            inputs.button_held = rescue_button_held_latched_read() != 0;
            break;
        }
    }

    enum rescue_boot_decision decision =
        rescue_boot_step(&policy, &inputs, RESCUE_TIMEOUT_MS);

    struct rescue_spi_nor nor = {0};
    enum rescue_spi_nor_result init = rescue_nor_litex_init(&nor);
    enum rescue_flash_probe_result probe = init == RESCUE_SPI_NOR_OK ? RESCUE_FLASH_PROBE_OK : RESCUE_FLASH_PROBE_UNKNOWN_ID;
    if (init == RESCUE_SPI_NOR_OK) {
        printf("Rescue: JEDEC %06lx capacity %lu erase %lu page %lu (profile, not physical qualification)\n", (unsigned long)nor.geometry.jedec_id, (unsigned long)nor.geometry.capacity, (unsigned long)nor.geometry.erase_size, (unsigned long)nor.geometry.page_size);
        /* SIMULATION ONLY. These are synthetic offsets, never stage to ISE. */
        static const struct rescue_region sim_map[] = {
            {RESCUE_REGION_BOOT,0,262144}, {RESCUE_REGION_RESCUE,2*262144,262144},
            {RESCUE_REGION_APP_A,3*262144,262144}, {RESCUE_REGION_APP_B,5*262144,262144},
            {RESCUE_REGION_IDENTITY,11*262144,262144}, {RESCUE_REGION_STATE_0,14*262144,262144},
            {RESCUE_REGION_STATE_1,8*262144,262144}
        };
        struct rescue_persistent_state state;
        enum rescue_inspection_result r=rescue_protected_inspect(&nor.geometry,sim_map,sizeof sim_map/sizeof sim_map[0],persistent_read,&nor,NULL,0,&state);
        puts("SIMULATION ONLY: synthetic persistent map; boot remains disabled");
        if (r==RESCUE_INSPECTION_OK) printf("SIM: identity=%d journal=%d\n",(int)state.identity_status,(int)state.journal_status);
        else printf("SIM: inspection failed %d\n",(int)r);

    } else {
        printf("Rescue: read-only NOR init failed (%d)\n", (int)init);
    }
    puts("Rescue: RECOVERY ONLY (diagnostic BIOS)");
    puts("Rescue: no validated identity, journal, or application slot");
    if (inputs.button_sampled)
        puts(inputs.button_held ? "Rescue: startup button held"
                               : "Rescue: startup button released");
    else
        puts("Rescue: startup button sampling timed out");
    puts(decision == RESCUE_RECOVERY_ONLY
         ? "Rescue: policy returned RECOVERY ONLY"
         : "Rescue: unexpected policy result; forcing RECOVERY ONLY");
#ifdef CSR_ETHMAC_BASE
    static const uint8_t mac[] = {MACADDR1, MACADDR2, MACADDR3,
                                  MACADDR4, MACADDR5, MACADDR6};
    uint32_t ip = IPTOINT((uint32_t)LOCALIP1, LOCALIP2, LOCALIP3, LOCALIP4);
    startup_probe = probe;
    eth_init();
    udp_start(mac, ip);
    udp_set_callback(rescue_diag_receive);
    set_idle_hook(udp_service);
#endif
    puts("Rescue: application boot disabled; UART console ready");
}
