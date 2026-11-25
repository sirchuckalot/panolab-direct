#include <stdio.h>
#include <string.h>

#include <generated/csr.h>
#include <generated/soc.h>

#include "rescue_bios.h"
#include "rescue_diag.h"
#include "rescue_boot_policy.h"
#include "rescue_flash_probe.h"
#include "rescue_spi_nor.h"
#include "rescue_protected_read.h"
#include "sim_upload.h"

#if !defined(CONFIG_BIOS_NO_BOOT) || defined(BIOS_CONSOLE_DISABLE)
#error "Rescue diagnostics require stock boot disabled and the console enabled"
#endif

#define RESCUE_TIMEOUT_MS (PANOLAB_AUTOBOOT_WINDOW_S * UINT32_C(1000))
_Static_assert(RESCUE_TIMEOUT_MS >= RESCUE_AUTOBOOT_MIN_MS &&
               RESCUE_TIMEOUT_MS <= RESCUE_AUTOBOOT_MAX_MS,
               "Rescue timeout outside policy domain");

#ifdef CSR_ETHMAC_BASE
#include <libliteeth/udp.h>
/* Declarations match the hash-guarded simulation UDP overlay. */
int sim_udp_peer_mac(uint8_t *mac);
int sim_udp_send_peer(uint32_t ip,const uint8_t *mac,uint16_t src,uint16_t dst,uint32_t length);
#include "readline.h"

_Static_assert(PANOLAB_RESCUE_API == RESCUE_DIAG_API_VERSION,
               "Generated API version differs from the diagnostic protocol");

static enum rescue_flash_probe_result startup_probe;

static uint64_t sim_clock_ms(void *ctx){
    (void)ctx;
    timer0_uptime_latch_write(1);
    return timer0_uptime_cycles_read()/(CONFIG_CLOCK_FREQUENCY/1000u);
}
static void sim_reply(void *ctx,const struct ns_peer *peer,const uint8_t *data,size_t n){
    (void)ctx;
    uint32_t ip=IPTOINT((uint32_t)peer->ip[0],(uint32_t)peer->ip[1],(uint32_t)peer->ip[2],(uint32_t)peer->ip[3]);
    memcpy(udp_get_tx_buffer(),data,n);
    (void)sim_udp_send_peer(ip,peer->mac,49153u,peer->port,n);
}
static void rescue_idle(void){udp_service();sim_upload_tick();}
static void rescue_diag_receive(uint32_t src_ip, uint16_t src_port,
                                uint16_t dst_port, void *data, uint32_t length)
{
    if (src_port == 0 ||
        (src_ip >> 24) == 0 || (src_ip >> 24) >= 224)
        return;

    if (dst_port == 49153u) {
        struct ns_peer peer={.ip={(uint8_t)(src_ip>>24),(uint8_t)(src_ip>>16),(uint8_t)(src_ip>>8),(uint8_t)src_ip},.port=src_port};
        if(sim_udp_peer_mac(peer.mac)) sim_upload_receive(&peer,data,length);
        return;
    }
    if(dst_port != RESCUE_DIAG_PORT) return;
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
        if (sim_upload_init(&nor.geometry)) puts("SIMULATION ONLY: RAM upload enabled; no physical flash writes");
        else puts("SIMULATION ONLY: RAM upload disabled");
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
    (void)sim_upload_session_init(sim_clock_ms,sim_reply);
    set_idle_hook(rescue_idle);
#endif
    puts("Rescue: application boot disabled; UART console ready");
}
