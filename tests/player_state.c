// SPDX-License-Identifier: MIT
// Compile the production state machine. Only the clock, NVS and radio boundary
// are simulated; no alternative implementation of the player is used.
#include <assert.h>
#include <stdio.h>
#include "../firmware-source/main/player.c"
#ifdef NDEBUG
#error "This state-machine harness requires assertions"
#endif

static int64_t clock_ms;
static bool power_ack;
static unsigned power_queries, persisted_off;
static uint8_t sequence;
int64_t esp_timer_get_time(void) { return clock_ms*1000; }
void esp_zb_get_extended_pan_id(uint8_t *out) { memcpy(out,plan_pan,8); }
esp_err_t nvs_set_u8(nvs_handle_t handle, const char *key, uint8_t value)
{ (void)handle; if (!strcmp(key,"off") && value) persisted_off++; return ESP_OK; }
esp_err_t nvs_commit(nvs_handle_t handle) { (void)handle; return ESP_OK; }
esp_err_t nvs_erase_key(nvs_handle_t handle, const char *key)
{ (void)handle; (void)key; return ESP_OK; }
void esp_zb_zdo_nwk_addr_req(esp_zb_zdo_nwk_addr_req_param_t *req,
    void (*cb)(esp_zb_zdp_status_t, esp_zb_zdo_nwk_addr_rsp_t *, void *), void *ctx)
{ (void)req; (void)cb; (void)ctx; assert(!"unexpected address resolution"); }
static void confirm(uint16_t dst, uint8_t ep, uint8_t *frame, size_t length, int status)
{
    esp_zb_apsde_data_confirm_t c={.dst_addr.addr_short=dst,
        .dst_endpoint=ep,.src_endpoint=20,.status=status,.asdu=frame,.asdu_length=length};
    bool accepted=hm_player_confirm(c); assert(accepted);
}
esp_err_t hm_send(uint16_t dst, uint8_t ep, uint16_t cluster,
    bool specific, int manufacturer, uint8_t command, const uint8_t *payload,
    size_t length, bool quiet, uint8_t *tsn)
{
    (void)quiet;
    *tsn=++sequence;
    uint8_t frame[HM_MAX_FRAME];
    size_t n=hm_frame(frame,specific,manufacturer,*tsn,command,payload,length);
    assert(cluster==6 && command==0 && length==2); power_queries++;
    confirm(dst,ep,frame,n,power_ack ? 0 : 1);
    return ESP_OK;
}
esp_err_t hm_send_animation(uint16_t dst, uint8_t ep, const uint8_t *p, size_t n, uint8_t *tsn)
{
    *tsn=++sequence;
    uint8_t frame[HM_MAX_FRAME]; size_t length=hm_frame(frame,true,0x100b,*tsn,0,p,n);
    // A successful unacknowledged animation confirm must NOT refresh liveness.
    confirm(dst,ep,frame,length,0); return ESP_OK;
}
static void reset(void)
{
    free(samples); samples=calloc(2,sizeof(sample_t)); assert(samples);
    sample_count=2; samples[0].length=samples[1].length=6;
    clock_ms=started=last_power_reply=last_target_ack=1000;
    last_power=0; next_due=1000; expires=0; ended=0;
    durable=playing=palette_mode=resolved=true;
    restoring=configuring=pending=power_pending=preserve_off=false;
    checking=sync_requested=pending_sync=resolving=false;
    state="playing";reason="requested_start"; fps=10; cycle_ms=4000;
    cleanup_count=1; check_count=1; step=0; retries=0;
    address=0x1234;endpoint=11;power_queries=persisted_off=0;
    power_ack=true;frames_sent=frames_acked=failures=skipped=0;
}
int main(void)
{
    reset();
    // Lost ZCL status responses for a whole minute, with acknowledged queries.
    for (clock_ms=1100;clock_ms<=61000;clock_ms+=100) {
        hm_player_tick(true); assert(playing && !restoring);
    }
    assert(power_queries>=15 && last_power_reply==1000 && last_target_ack>58000);
    puts("PASS acknowledged power queries survive missing attribute responses");

    reset(); power_ack=false;
    for (clock_ms=1100;clock_ms<=16000;clock_ms+=100) {
        hm_player_tick(true); assert(playing);
    }
    // Let tick stop before emitting restoration packets: this test observes
    // the durable transition, not the separate readback recovery protocol.
    clock_ms=16001;next_due=clock_ms+1;hm_player_tick(true);
    assert(!playing && restoring && durable && !strcmp(reason,"target_unresponsive"));
    assert(last_target_ack==1000 && frames_acked>0);
    puts("PASS failed APS queries stop despite successful animation MAC confirms");

    reset();
    for (clock_ms=1100;clock_ms<=21000;clock_ms+=100) hm_player_tick(true);
    assert(playing && power_pending && last_power_reply==1000);
    uint8_t off[]={0x18,power_tsn,1,0,0,0,0x10,0};
    esp_zb_apsde_data_ind_t ind={.src_short_addr=address,.src_endpoint=endpoint,
        .dst_endpoint=20,.cluster_id=6,.asdu=off,.asdu_length=sizeof(off)};
    bool accepted=hm_player_receive(ind);assert(accepted);
    assert(!playing && restoring && durable && preserve_off && persisted_off==1);
    assert(!strcmp(reason,"external_off"));
    puts("PASS external off after prolonged ACK-only playback persists recovery intent");

    reset();clock_ms=2000;hm_player_tick(true);assert(power_pending);
    uint8_t query[]={0x10,power_tsn,0,0,0};
    esp_zb_apsde_data_confirm_t c={.dst_addr.addr_short=address,.dst_endpoint=endpoint,
        .src_endpoint=20,.asdu=query,.asdu_length=sizeof(query)};
    clock_ms=3000;int64_t unchanged=last_target_ack;
    c.dst_addr.addr_short++;accepted=hm_player_confirm(c);assert(!accepted && last_target_ack==unchanged);
    c.dst_addr.addr_short=address;c.dst_endpoint++;accepted=hm_player_confirm(c);assert(!accepted && last_target_ack==unchanged);
    c.dst_endpoint=endpoint;c.src_endpoint++;accepted=hm_player_confirm(c);assert(!accepted && last_target_ack==unchanged);
    c.src_endpoint=20;query[1]++;accepted=hm_player_confirm(c);assert(!accepted && last_target_ack==unchanged);
    query[1]=power_tsn;c.asdu_length--;accepted=hm_player_confirm(c);assert(!accepted && last_target_ack==unchanged);
    c.asdu_length=sizeof(query);accepted=hm_player_confirm(c);assert(accepted && last_target_ack==clock_ms);
    // Correct reply before its delayed ACK: it must no longer match a query.
    power_pending=false;clock_ms=4000;accepted=hm_player_confirm(c);
    assert(!accepted && last_target_ack==3000);
    puts("PASS incorrect or late power confirmations cannot extend liveness");
    free(samples);samples=NULL;
    return 0;
}
