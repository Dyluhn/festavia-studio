// SPDX-License-Identifier: MIT
// Durable on-device playback and recovery. No host heartbeat is needed to play.
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "player.h"
#include "wire.h"
#include "esp_timer.h"
#include "nvs.h"
#include "esp_zigbee_core.h"
#include "zdo/esp_zigbee_zdo_command.h"

#define MAX_STEPS 16
#define MAX_POSITIONS 255
#define MAX_PAINT_STEPS (4 + 2 * ((MAX_POSITIONS + 4) / 5))
#define MAX_FRAMES 64
#define MAX_VERIFY 8
#define TARGET_TIMEOUT_MS 15000
typedef struct {
    uint16_t cluster, length, expected_length;
    int manufacturer;
    uint8_t command, type, response_command;
    uint8_t payload[HM_MAX_PAYLOAD], expected[HM_MAX_PAYLOAD];
} packet_t;
typedef struct { uint16_t length; uint8_t data[HM_MAX_PAYLOAD]; } sample_t;
static nvs_handle_t store;
static packet_t cleanup[MAX_STEPS], checks[MAX_VERIFY], setup[MAX_STEPS], ready_checks[MAX_VERIFY];
static size_t cleanup_count, check_count, setup_count, ready_count, step;
static sample_t *samples;
static int sample_count, fps = 10, duration_ms, retries, last_status, last_slot, cycle_ms=4000;
static uint8_t ieee[8], plan_pan[8], endpoint, pending_tsn, pending_cmd;
static uint16_t address, pending_cluster;
static uint8_t last_payload[195];
static uint16_t last_length, sample_index;
static uint32_t counter, frames_sent, frames_acked, failures, skipped;
static int64_t next_due, started, first_frame, ended, expires, pending_until, resolve_until, armed_until, last_power;
static bool durable, playing, restoring, checking, pending, waiting_reply, resolving, resolved, preserve_off, power_pending, configuring, restore_power_checked, sync_requested, pending_sync;
static uint8_t power_tsn;
static const char *state = "idle", *reason = "none";
static bool palette_mode, bank_acked, pending_current_bank;
static int64_t last_power_reply, last_target_ack;
static bool hue_takeover, releasing, playback_persisted;
static int64_t hue_deadline, release_due, release_timeout;
static unsigned release_lost_confirms;
static packet_t color_probe;
static bool color_probe_queued, pending_color_probe;
static unsigned color_probe_count;
static const char *failure_cause="none", *failure_stage="none";
static size_t failure_step;
static unsigned animation_timeouts;
// A retained scene is a finite, acknowledged paint burst. The lamp holds its
// colors after its original geometry has been verified; there is no map loop.
static packet_t *paint;
static size_t paint_count, paint_step, paint_check_step;
static bool retained_mode, pending_paint, pending_paint_check, geometry_dirty, geometry_release;

static int64_t now(void) { return esp_timer_get_time() / 1000; }
static bool number(const cJSON *obj, const char *key, int min, int max, int *out)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(obj, key);
    if (!cJSON_IsNumber(v) || !isfinite(v->valuedouble) || v->valuedouble < min ||
        v->valuedouble > max || v->valuedouble != (double)v->valueint) return false;
    *out = v->valueint;
    return true;
}
static const char *str(const cJSON *obj, const char *key)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(obj, key);
    return cJSON_IsString(v) ? v->valuestring : NULL;
}
static cJSON *result(bool ok, const char *error)
{
    cJSON *r = cJSON_CreateObject();
    cJSON_AddBoolToObject(r, "ok", ok);
    if (error) cJSON_AddStringToObject(r, "error", error);
    cJSON_AddStringToObject(r, "state", state);
    cJSON_AddStringToObject(r, "reason", reason);
    cJSON_AddBoolToObject(r, "armed", durable);
    cJSON_AddBoolToObject(r, "playing", playing);
    cJSON_AddBoolToObject(r, "preserve_off", preserve_off);
    cJSON_AddBoolToObject(r, "native_palette_supported", true);
    cJSON_AddBoolToObject(r, "native_fit_supported", true);
    cJSON_AddNumberToObject(r, "native_positions_max", MAX_POSITIONS);
    cJSON_AddNumberToObject(r, "retained_paint_steps_max", MAX_PAINT_STEPS);
    cJSON_AddBoolToObject(r, "hue_takeover_supported", true);
    cJSON_AddBoolToObject(r, "hue_takeover", hue_takeover);
    cJSON_AddNumberToObject(r,"release_lost_confirms",release_lost_confirms);
    cJSON_AddNumberToObject(r, "hue_watchdog_remaining_ms", playing && hue_takeover ? hue_deadline-now() : -1);
    cJSON_AddStringToObject(r, "transport", retained_mode ? "retained" : palette_mode ? "palette" : "segments");
    cJSON_AddBoolToObject(r,"retained_pucks_supported",true);
    cJSON_AddBoolToObject(r,"applying",playing && retained_mode && !bank_acked);
    cJSON_AddNumberToObject(r,"paint_step",paint_step);
    cJSON_AddNumberToObject(r,"paint_steps",paint_count);
    cJSON_AddBoolToObject(r, "aps_acknowledged", !(palette_mode && sample_count > 1));
    cJSON_AddNumberToObject(r, "color_restore_probes", color_probe_count);
    cJSON_AddStringToObject(r, "failure_cause", failure_cause);
    cJSON_AddStringToObject(r, "failure_stage", failure_stage);
    cJSON_AddNumberToObject(r, "failure_step", failure_step);
    cJSON_AddNumberToObject(r, "animation_timeouts", animation_timeouts);
    cJSON_AddNumberToObject(r, "power_response_age_ms", started ? now()-last_power_reply : -1);
    cJSON_AddNumberToObject(r, "target_ack_age_ms", started ? now()-last_target_ack : -1);
    cJSON_AddNumberToObject(r, "fps", fps);
    cJSON_AddNumberToObject(r, "frames", sample_count);
    cJSON_AddNumberToObject(r, "cycle_ms", cycle_ms);
    cJSON_AddNumberToObject(r, "sent", frames_sent);
    cJSON_AddNumberToObject(r, "acked", frames_acked);
    cJSON_AddNumberToObject(r, "failures", failures);
    cJSON_AddNumberToObject(r, "skipped", skipped);
    cJSON_AddNumberToObject(r, "elapsed_ms", started ? (ended ? ended : now()) - started : 0);
    cJSON_AddNumberToObject(r, "playback_ms", first_frame ? (ended ? ended : now()) - first_frame : 0);
    cJSON_AddNumberToObject(r, "last_aps_status", last_status);
    cJSON_AddNumberToObject(r,"counter",counter);
    cJSON_AddNumberToObject(r,"sample_index",sample_index);
    char payload[391];hm_hex(last_payload,last_length,payload);cJSON_AddStringToObject(r,"last_payload",payload);
    cJSON_AddNumberToObject(r, "duration_ms", duration_ms);
    cJSON_AddNumberToObject(r, "step", step);
    char text[17]; hm_eui64_text(ieee, text);
    cJSON_AddStringToObject(r, "target", text);
    return r;
}
static bool packets(const cJSON *array, packet_t *out, int max, size_t *count)
{
    int n = cJSON_GetArraySize(array);
    if (!cJSON_IsArray(array) || n < 1 || n > max) return false;
    for (int i = 0; i < n; i++) {
        const cJSON *obj = cJSON_GetArrayItem(array, i);
        packet_t *p = &out[i];
        int cluster, cmd, type, mfg, response = 0;
        int length = hm_unhex(str(obj, "payload"), p->payload, sizeof(p->payload));
        if (length < 0 || !number(obj,"cluster",0,65535,&cluster) ||
            !number(obj,"command",0,255,&cmd) || !number(obj,"frame_type",0,1,&type) ||
            !number(obj,"manufacturer",-1,65535,&mfg)) return false;
        p->cluster=cluster; p->command=cmd; p->type=type; p->manufacturer=mfg; p->length=length;
        p->expected_length=0;
        if (cJSON_HasObjectItem(obj,"expect")) {
            int len = hm_unhex(str(obj,"expect"),p->expected,sizeof(p->expected));
            if (len < 1 || !number(obj,"response_command",0,255,&response)) return false;
            p->expected_length=len;
        }
        p->response_command=response;
    }
    *count = n;
    return true;
}
static bool parse_plan(const cJSON *obj)
{
    uint8_t target[8], pan[8]; int ep;
    // Parse into temporary storage so malformed plans cannot alter a live journal.
    packet_t *tmp = calloc(2 * (MAX_STEPS + MAX_VERIFY), sizeof(packet_t));
    if (!tmp) return false;
    size_t n=0, v=0, ns=0, vs=0;
    bool valid = hm_eui64(str(obj,"ieee"),target) && hm_eui64(str(obj,"extpan"),pan) && number(obj,"endpoint",1,240,&ep) &&
        packets(cJSON_GetObjectItemCaseSensitive(obj,"restore"),tmp,MAX_STEPS,&n) &&
        packets(cJSON_GetObjectItemCaseSensitive(obj,"verify"),tmp+MAX_STEPS,MAX_VERIFY,&v) &&
        packets(cJSON_GetObjectItemCaseSensitive(obj,"setup"),tmp+MAX_STEPS+MAX_VERIFY,MAX_STEPS,&ns) &&
        packets(cJSON_GetObjectItemCaseSensitive(obj,"ready"),tmp+2*MAX_STEPS+MAX_VERIFY,MAX_VERIFY,&vs);
    for (size_t i=0; valid && i<v; i++) valid = tmp[MAX_STEPS+i].expected_length > 0;
    for (size_t i=0; valid && i<vs; i++) valid = tmp[2*MAX_STEPS+MAX_VERIFY+i].expected_length > 0;
    if (valid) {
        memcpy(ieee,target,8); memcpy(plan_pan,pan,8); endpoint=ep; cleanup_count=n; check_count=v;
        setup_count=ns; ready_count=vs;
        memcpy(setup,tmp+MAX_STEPS+MAX_VERIFY,ns*sizeof(packet_t));
        memcpy(ready_checks,tmp+2*MAX_STEPS+MAX_VERIFY,vs*sizeof(packet_t));
        memcpy(cleanup,tmp,n*sizeof(packet_t)); memcpy(checks,tmp+MAX_STEPS,v*sizeof(packet_t));
    }
    free(tmp);
    return valid;
}
static bool retained_program(packet_t *p, size_t n, unsigned positions)
{
    // Every temporary map must cover the entire fixture. Only singleton
    // regions receive colors, and the final packets restore captured geometry.
    if (n<5 || n>MAX_PAINT_STEPS || positions<1 || positions>MAX_POSITIONS || p[0].command!=3) return false;
    bool covered[MAX_POSITIONS]={0}; uint16_t aliases[10]={0}; uint8_t starts[10],lengths[10];
    unsigned alias_count=0,map_count=0; uint32_t previous=0;
    for (size_t j=0;j<n;j++) {
        packet_t *v=&p[j]; const uint8_t *b=v->payload; unsigned z=v->length;
        if (v->cluster!=0xfc01 || v->manufacturer!=0x100b || v->type!=1 || z>76) return false;
        if (v->command==3) {
            if (j!=0 || z!=6 || memcmp(b,"\0\1\0\0\0\0",6)) return false;
        } else if (v->command==7) {
            if (z<4 || b[0]!=0 || b[1]<1 || b[1]>10 || z!=2u+2u*b[1]) return false;
            alias_count=b[1];
            for (unsigned a=0;a<alias_count;a++) {
                aliases[a]=b[2+2*a]|b[3+2*a]<<8;
                if (!hm_unicast(aliases[a],1)) return false;
                for (unsigned k=0;k<a;k++) if (aliases[k]==aliases[a]) return false;
            }
        } else if (v->command==5) {
            if (z<4 || b[0]!=0 || b[1]<1 || b[1]>10 || z!=2u+2u*b[1]) return false;
            map_count=b[1]; unsigned end=0;
            for (unsigned a=0;a<map_count;a++) {
                starts[a]=b[2+2*a];lengths[a]=b[3+2*a];
                if (starts[a]!=end || !lengths[a]) return false;
                end+=lengths[a];
            }
            if (end!=positions) return false;
        } else if (v->command==1) {
            if (z<13 || (z-6)%7 || !map_count || map_count!=alias_count) return false;
            uint32_t seq=b[0]|(uint32_t)b[1]<<8|(uint32_t)b[2]<<16|(uint32_t)b[3]<<24;
            if (seq<=previous) return false;
            previous=seq;
            for (unsigned a=6;a<z;a+=7) {
                uint16_t id=b[a]|b[a+1]<<8; unsigned k;
                if (b[a+2]&31) return false;
                for (k=0;k<alias_count && aliases[k]!=id;k++);
                if (k==alias_count || lengths[k]!=1) return false;
                covered[starts[k]]=true;
            }
        } else return false;
    }
    for (unsigned i=0;i<positions;i++) if (!covered[i]) return false;
    for (unsigned k=0;k<2;k++) {
        packet_t *last=&p[n-2+k]; bool found=false;
        if (last->command!=(k ? 7 : 5)) return false;
        for (size_t i=0;i<ready_count;i++) {
            packet_t *v=&ready_checks[i];
            if (v->cluster==0xfc01 && v->command==(k ? 6 : 4) &&
                v->expected_length==last->length+1 && v->expected[0]==0 &&
                !memcmp(v->expected+1,last->payload,last->length)) found=true;
        }
        if (!found) return false;
    }
    return true;
}
static bool geometry_only(void)
{
    // A handoff during painting repairs geometry without replaying power,
    // brightness or colors. The original journal survives a reboot.
    packet_t out[2],verify[2]; unsigned n=0,v=0;
    for (size_t i=0;i<cleanup_count;i++)
        if (cleanup[i].cluster==0xfc01 && (cleanup[i].command==5 || cleanup[i].command==7) && n<2) out[n++]=cleanup[i];
    for (size_t i=0;i<check_count;i++)
        if (checks[i].cluster==0xfc01 && (checks[i].command==4 || checks[i].command==6) && v<2) verify[v++]=checks[i];
    if (n!=2 || v!=2) return false;
    memcpy(cleanup,out,sizeof(out));cleanup_count=2;
    memcpy(checks,verify,sizeof(verify));check_count=2;
    geometry_release=true;retained_mode=false;geometry_dirty=false;
    playing=releasing=configuring=checking=pending=pending_paint=pending_paint_check=false;
    restoring=durable;step=0;retries=0;restore_power_checked=true;
    next_due=now();state="releasing_geometry";reason="hue_takeover";
    return true;
}
// Release deliberately emits no fixture writes. Persist the tombstone before
// discarding the recovery plan so reboot cannot replay an old scene over Hue.
static bool release_begin(const char *why)
{
    if (playing) ended=now();
    playing=restoring=configuring=checking=false;
    sync_requested=pending_sync=waiting_reply=power_pending=false;
    color_probe_queued=pending_color_probe=false;
    release_due=now()+2000;
    release_timeout=now()+30000;release_lost_confirms=0; // Drain the bounded in-flight native frame.
    pending=false;releasing=true;state="releasing";reason=why;
    esp_err_t error=nvs_set_u8(store,"yield",1);
    if (error==ESP_OK) error=nvs_commit(store);
    if (error!=ESP_OK) {state="recovery_required";reason="release_persist_failed";return false;}
    return true;
}
static void release_tick(void)
{
    if (now()<release_due) return;
    unsigned outstanding=hm_pending_transfers();
    if (outstanding && now()<release_timeout) return;
    release_lost_confirms=outstanding;
    if (geometry_dirty) {
        if (!outstanding && geometry_only()) return;
        state="recovery_required";reason="geometry_release_unconfirmed";return;
    }
    // Recommit the tombstone on retries before touching the old capsule.
    esp_err_t error=nvs_set_u8(store,"yield",1);
    if (error==ESP_OK) error=nvs_commit(store);
    if (error==ESP_OK) {
        esp_err_t erased=nvs_erase_key(store,"journal");
        if (erased!=ESP_OK && erased!=ESP_ERR_NVS_NOT_FOUND) error=erased;
    }
    if (error==ESP_OK) error=nvs_commit(store);
    if (error!=ESP_OK) {release_due=now()+1000;state="releasing";return;}
    durable=releasing=false;free(samples);samples=NULL;sample_count=0;
    state="released";
}
static void restore_begin(const char *why, bool off)
{
    if (playing) ended=now();
    playing=false; pending=false; pending_sync=false; sync_requested=false; waiting_reply=false; power_pending=false;
    restoring=durable; configuring=false; checking=false; step=0; retries=0;
    color_probe_queued=pending_color_probe=false; color_probe_count=0;
    pending_paint=pending_paint_check=false;
    // This session already resolved the exact IEEE on the approved PAN.
    // Retain that binding for immediate restoration. Globals start unresolved
    // at boot, so durable reboot recovery still performs a fresh ZDO lookup.
    resolving=false; restore_power_checked=false; next_due=now(); preserve_off |= off;
    state=durable ? "restoring" : "idle"; reason=why;
    if (preserve_off) {
        // Persist external-off intent across a restart during restoration.
        nvs_set_u8(store,"off",1); nvs_commit(store);
    }
}
void hm_player_init(void)
{
    ESP_ERROR_CHECK(nvs_open("hm_player",NVS_READWRITE,&store));
    uint8_t yielded=0;
    nvs_get_u8(store,"yield",&yielded);
    uint8_t dirty=0;nvs_get_u8(store,"paint",&dirty);geometry_dirty=dirty;
    if (yielded && !dirty) {durable=true;release_begin("hue_takeover");release_due=now();release_tick();return;}
    size_t size=0;
    if (nvs_get_str(store,"journal",NULL,&size)==ESP_OK && size && size < 20000) {
        char *body=malloc(size);
        if (body && nvs_get_str(store,"journal",body,&size)==ESP_OK) {
            cJSON *obj=cJSON_Parse(body);
            durable=parse_plan(obj);
            cJSON_Delete(obj);
        }
        free(body);
        uint8_t off=0; nvs_get_u8(store,"off",&off); preserve_off=off;
        uint8_t takeover=0;nvs_get_u8(store,"take",&takeover);hue_takeover=takeover;
        uint8_t played=0;nvs_get_u8(store,"played",&played);playback_persisted=played;
        if (durable && (yielded || (hue_takeover && played))) {
            if (dirty) {
                nvs_set_u8(store,"yield",1);nvs_commit(store);
                if (!geometry_only()) {state="recovery_required";reason="geometry_journal_invalid";}
            } else release_begin("restart_yield");
        }
        else if (durable) restore_begin("boot_recovery",preserve_off);
        else { state="recovery_required"; reason="invalid_saved_journal"; }
    }
}
bool hm_player_busy(void) { return durable; }
static void resolved_cb(esp_zb_zdp_status_t status, esp_zb_zdo_nwk_addr_rsp_t *rsp, void *ctx)
{
    (void)ctx;
    if (!resolving) return;
    resolving=false;
    if (status==ESP_ZB_ZDP_STATUS_SUCCESS && rsp && memcmp(rsp->ieee_addr,ieee,8)==0 &&
        hm_unicast(rsp->nwk_addr,endpoint)) {
        address=rsp->nwk_addr; resolved=true; retries=0;
    } else { next_due=now()+1000; retries++; }
}
static esp_err_t send_packet(packet_t *p, bool quiet, uint8_t *tsn)
{
    uint8_t data[HM_MAX_PAYLOAD]; memcpy(data,p->payload,p->length);
    // The host specifies the final power command and its readback. Respect a
    // Hue/app/manual off observed during playback or an explicit off request.
    uint8_t command=p->command;
    if (preserve_off && p->cluster==6 && p->type==1 && command==1) command=0;
    return hm_send(address,endpoint,p->cluster,p->type,p->manufacturer,command,data,p->length,quiet,tsn);
}
static void advance(void)
{
    pending=false; waiting_reply=false; retries=0; step++; next_due=now()+150;
}
static void failure(const char *cause)
{
    failure_cause=cause;failure_step=step;
    failure_stage=playing ? "playback" : configuring ? (checking ? "ready" : "setup") : (checking ? "verify" : "restore");
    if (pending_color_probe) {color_probe_queued=true;pending_color_probe=false;}
    if (playing && palette_mode && sample_count > 1) {
        // A newer color supersedes a lost frame. Do not pause the animation or
        // retry stale colors. Acknowledged power reads below monitor liveness.
        pending=false; waiting_reply=false; failures++; skipped++; retries=0;
        next_due=now()+1000/fps; return;
    }
    pending=false; waiting_reply=false; failures++; retries++; next_due=now()+300;
    if (playing && retries>=3) {
        if (hue_takeover && (palette_mode || retained_mode)) release_begin("delivery_failed");
        else restore_begin("delivery_failed",false);
    }
    else if (restoring && retries>=3 && configuring) restore_begin("setup_failed",false);
    else if (restoring && retries>=3) {
        restoring=false; state="recovery_required"; reason="restore_unconfirmed";
    }
}
bool hm_player_confirm(esp_zb_apsde_data_confirm_t c)
{
    uint8_t tsn,cmd; size_t h;
    if (!hm_zcl_header(c.asdu,c.asdu_length,&tsn,&cmd,&h)) return false;
    if (power_pending && tsn==power_tsn && c.dst_addr.addr_short==address &&
        c.dst_endpoint==endpoint && c.src_endpoint==20 && cmd==0 &&
        c.asdu_length==h+2 && c.asdu[h]==0 && c.asdu[h+1]==0) {
        // Unlike animation frames, power queries request an end-to-end APS
        // acknowledgement. Its success proves the target is reachable even
        // when the independent ZCL attribute response is lost. Keep waiting
        // for that response so a real external off still stops playback.
        if (c.status==0) last_target_ack=now();
        return true;
    }
    if (!pending || tsn!=pending_tsn || c.dst_addr.addr_short!=address) return false;
    last_status=c.status;
    if (c.status) failure("aps_status");
    else if (pending_paint) {
        // A paint/configuration packet waits for its matching ZCL reply.
        last_target_ack=now();
    }
    else if (pending_color_probe) {
        pending=false;pending_color_probe=false;color_probe_queued=false;
        retries=0;next_due=now()+200;
    }
    else if (playing && pending_sync) { pending=false; pending_sync=false; sync_requested=false; retries=0; next_due=now(); }
    else if (playing) {
        frames_acked++; if (pending_current_bank) bank_acked=true;
        if (!playback_persisted && nvs_set_u8(store,"played",1)==ESP_OK && nvs_commit(store)==ESP_OK) playback_persisted=true;
        pending=false; retries=0;
    }
    else if (restoring && !checking) advance();
    // Verification waits for the matching ZCL response after APS acknowledgement.
    return true;
}
bool hm_player_receive(esp_zb_apsde_data_ind_t ind)
{
    if (ind.src_short_addr!=address || ind.src_endpoint!=endpoint || ind.dst_endpoint!=20) return false;
    uint8_t tsn,cmd; size_t h;
    if (!hm_zcl_header(ind.asdu,ind.asdu_length,&tsn,&cmd,&h)) return false;
    const uint8_t *p=ind.asdu+h; size_t n=ind.asdu_length-h;
    if (power_pending && tsn==power_tsn && ind.cluster_id==6 && cmd==1) {
        power_pending=false;
        if (n==5 && p[0]==0 && p[1]==0 && p[2]==0 && p[3]==0x10 && p[4]<=1)
            last_power_reply=now();
        if (n==5 && p[0]==0 && p[1]==0 && p[2]==0 && p[3]==0x10 && p[4]==0) {
            if (playing && hue_takeover) release_begin("external_off");
            else if (playing) restore_begin("external_off",true);
            else if (!configuring) { preserve_off=true; nvs_set_u8(store,"off",1); nvs_commit(store); }
        }
        restore_power_checked=true;
        return true;
    }
    if (!pending || tsn!=pending_tsn || ind.cluster_id!=pending_cluster) return false;
    if (pending_paint) {
        if (pending_paint_check) {
            packet_t *v=&ready_checks[paint_check_step];
            if (cmd!=v->response_command) return false;
            if (n!=v->expected_length || memcmp(p,v->expected,n)) failure("paint_readback_mismatch");
            else {pending=false;pending_paint=pending_paint_check=false;paint_check_step++;retries=0;next_due=now()+150;}
        } else {
            packet_t *v=&paint[paint_step];
            bool specific=(ind.asdu[0]&3)==1;
            bool match=(specific && cmd==v->command && n>=1) || (!specific && cmd==11 && n==2 && p[0]==v->command);
            if (!match) return false;
            uint8_t status=specific ? p[0] : p[1];
            if (status) failure("paint_fixture_rejected");
            else {pending=false;pending_paint=false;paint_step++;retries=0;next_due=now()+150;}
        }
        return true;
    }
    if (restoring && checking && cmd==pending_cmd) {
        packet_t *check=configuring ? &ready_checks[step] : &checks[step];
        uint8_t expected[HM_MAX_PAYLOAD]; memcpy(expected,check->expected,check->expected_length);
        if (preserve_off && check->cluster==6 && check->expected_length==5) expected[4]=0;
        if (n==check->expected_length && memcmp(p,expected,n)==0) advance();
        else if (!configuring && n==23 && check->cluster==0x300 && check->length==8 &&
                 memcmp(check->payload,"\x03\x00\x04\x00\x07\x00\x08\x00",8)==0 &&
                 check->expected_length==23 && expected[22]==1 &&
                 memcmp(p,"\x03\x00\x00\x21",4)==0 && memcmp(p+6,"\x04\x00\x00\x21",4)==0 &&
                 memcmp(p+12,"\x07\x00\x00\x21",4)==0 && memcmp(p+18,"\x08\x00\x00\x30",4)==0) {
            uint16_t x=expected[4]|expected[5]<<8,y=expected[10]|expected[11]<<8,a,b;
            bool found=false;
            while (color_probe_count<49 && !found)
                found=hm_xy_restore_probe(x,y,color_probe_count++,&a,&b);
            if (!found) failure("xy_probe_exhausted");
            else {
                memset(&color_probe,0,sizeof(color_probe));
                color_probe.cluster=0x300;color_probe.command=7;color_probe.type=1;color_probe.manufacturer=-1;
                color_probe.length=8;color_probe.payload[0]=a;color_probe.payload[1]=a>>8;
                color_probe.payload[2]=b;color_probe.payload[3]=b>>8;
                color_probe.payload[6]=1;color_probe.payload[7]=1; // ExecuteIfOff, no transition.
                pending=false;waiting_reply=false;retries=0;
                color_probe_queued=true;next_due=now();
            }
        } else failure("readback_mismatch");
        return true;
    }
    return false;
}
void hm_player_tick(bool approved)
{
    int64_t t=now();
    if (releasing) {release_tick();return;}
    if (playing && hue_takeover && t>=hue_deadline) {release_begin("hue_watchdog_expired");return;}
    if (!approved || (!playing && !restoring && !durable)) return;
    uint8_t pan[8]; esp_zb_get_extended_pan_id(pan);
    if (durable && memcmp(pan,plan_pan,8)!=0) { playing=false; restoring=false; state="recovery_required"; reason="network_changed"; return; }
    if (durable && !playing && !restoring && strcmp(state,"armed")==0 && t>=armed_until)
        restore_begin("prepare_expired",false);
    if (playing && expires && t>=expires) {
        if (hue_takeover && (palette_mode || retained_mode)) release_begin("duration_complete");
        else restore_begin("duration_complete",false);
    }
    if (releasing) {release_tick();return;}
    int64_t last_contact=last_power_reply>last_target_ack ? last_power_reply : last_target_ack;
    if (playing && ((palette_mode && sample_count > 1) || retained_mode) && t-last_contact>TARGET_TIMEOUT_MS)
        {if (hue_takeover) release_begin("target_unresponsive");else restore_begin("target_unresponsive",false);}
    if (releasing) {release_tick();return;}
    if (!playing && !restoring) return;
    if (!resolved) {
        if (resolving && t>resolve_until) { resolving=false; retries++; next_due=t+1000; }
        if (!resolving && t>=next_due) {
            if (retries>=3) { playing=false; restoring=false; state="recovery_required"; reason="target_unreachable"; return; }
            esp_zb_zdo_nwk_addr_req_param_t req={.dst_nwk_addr=0xfffd,.request_type=0};
            memcpy(req.ieee_addr_of_interest,ieee,8); resolving=true; resolve_until=t+6000;
            esp_zb_zdo_nwk_addr_req(&req,resolved_cb,NULL);
        }
        return;
    }
    if (pending && t>pending_until) {
        if (playing && palette_mode && sample_count>1) animation_timeouts++;
        failure("confirmation_timeout");
    }
    if (power_pending && t-last_power>3000) {
        power_pending=false;
        if (restoring && !configuring) { preserve_off=true; restore_power_checked=true; nvs_set_u8(store,"off",1); nvs_commit(store); }
    }
    if (pending || t<next_due) return;
    if (restoring && !configuring && !restore_power_checked) {
        if (!power_pending) {
            uint8_t p[]={0,0}; last_power=t;
            power_pending=true;
            if (hm_send(address,endpoint,6,false,-1,0,p,sizeof(p),false,&power_tsn)!=ESP_OK) {
                power_pending=false; restore_power_checked=true;
            }
        }
        return;
    }
    if (playing) {
        if (sync_requested) {
            uint8_t p[]={0,1,counter,counter>>8,counter>>16,counter>>24};
            pending=true;pending_sync=true;pending_until=t+2000;
            if (hm_send(address,endpoint,0xfc01,true,0x100b,3,p,sizeof(p),false,&pending_tsn)!=ESP_OK && pending) failure("send_rejected");
            return;
        }
        // Keep Hue's power state authoritative while this device owns colors.
        if (t-last_power>=1000 && !power_pending) {
            uint8_t p[]={0,0}; last_power=t;
            power_pending=true;
            if (hm_send(address,endpoint,6,false,-1,0,p,sizeof(p),false,&power_tsn)!=ESP_OK) power_pending=false;
            next_due=t+20; return;
        }
        if (retained_mode) {
            if (bank_acked) return;
            if (!geometry_dirty) return; // Load never starts geometry writes.
            if (paint_step>=paint_count && paint_check_step>=ready_count) {
                esp_err_t error=nvs_set_u8(store,"paint",0);
                if (error==ESP_OK) error=nvs_set_u8(store,"played",1);
                if (error==ESP_OK) error=nvs_commit(store);
                if (error!=ESP_OK) {restore_begin("paint_commit_failed",false);return;}
                geometry_dirty=false;playback_persisted=bank_acked=true;
                frames_acked++;state="playing";return;
            }
            pending_paint=true;pending_paint_check=paint_step>=paint_count;
            packet_t *v=pending_paint_check ? &ready_checks[paint_check_step] : &paint[paint_step];
            pending=true;pending_until=t+4000;pending_cluster=v->cluster;
            pending_cmd=v->response_command;
            if (send_packet(v,false,&pending_tsn)!=ESP_OK && pending) failure("send_rejected");
            if (!first_frame) first_frame=t;
            if (!frames_sent) frames_sent=1;
            return;
        }
        // A static native palette persists in the fixture. Keep power/timeout
        // monitoring alive without retransmitting an unchanged palette.
        if (palette_mode && sample_count == 1 && bank_acked) return;
        int slot=(t-started)*fps/1000;
        unsigned index=(unsigned)(((t-started)%cycle_ms)*sample_count/cycle_ms);
        if (last_slot>=0 && slot>last_slot+1) skipped+=slot-last_slot-1;
        last_slot=slot;
        sample_index=index;
        sample_t *s=&samples[index]; uint8_t p[HM_MAX_PAYLOAD]; memcpy(p,s->data,s->length);
        if (!palette_mode) {
            p[0]=counter; p[1]=counter>>8; p[2]=counter>>16; p[3]=counter>>24;
        }
        counter++;
        last_length=s->length;memcpy(last_payload,p,last_length);
        // The stack may complete a request before its call returns. Publish
        // correlation/ownership before handing it the copied output buffer.
        // A delayed confirmation must not freeze motion for two seconds.
        // The SDK owns a copy until its callback; only this presentation wait
        // expires. New frames remain paced by fps and this single pending slot.
        pending_current_bank=true; pending=true;
        pending_until=t+(palette_mode && sample_count>1 ? 500 : 2000);
        esp_err_t sent = palette_mode && sample_count > 1 ?
            hm_send_animation(address,endpoint,p,s->length,&pending_tsn) :
            hm_send(address,endpoint,palette_mode ? 0xfc03 : 0xfc01,true,0x100b,
                    palette_mode ? 0 : 1,p,s->length,true,&pending_tsn);
        if (sent!=ESP_OK) { if (pending) failure("send_rejected"); return; }
        if (!first_frame) first_frame=t;
        frames_sent++;
        next_due=t+1000/fps; return;
    }
    if (restoring && checking && color_probe_queued) {
        pending=true;pending_color_probe=true;pending_until=t+4000;
        pending_cluster=0x300;pending_cmd=0;
        if (send_packet(&color_probe,false,&pending_tsn)!=ESP_OK && pending) failure("send_rejected");
        return;
    }
    size_t count=checking ? (configuring ? ready_count : check_count) : (configuring ? setup_count : cleanup_count);
    if (step>=count) {
        if (!checking) { checking=true; step=0; next_due=t+1300; return; }
        if (configuring) {
            configuring=false; restoring=false; state="armed"; reason="setup_verified"; armed_until=t+120000; return;
        }
        // Only an exact matching readback retires the durable journal.
        if (nvs_set_u8(store,"paint",0)!=ESP_OK || nvs_erase_key(store,"journal")!=ESP_OK || nvs_commit(store)!=ESP_OK) {
            restoring=false; state="recovery_required"; reason="journal_retire_failed"; return;
        }
        durable=false; restoring=false;geometry_dirty=false;
        state=geometry_release ? "released" : "restored";geometry_release=false;
        free(samples); samples=NULL; return;
    }
    packet_t *p=checking ? (configuring ? &ready_checks[step] : &checks[step]) : (configuring ? &setup[step] : &cleanup[step]);
    pending=true; waiting_reply=checking; pending_cluster=p->cluster; pending_cmd=p->response_command;
    pending_until=t+4000;
    if (send_packet(p,false,&pending_tsn)!=ESP_OK && pending) failure("send_rejected");
}
cJSON *hm_player_command(const cJSON *obj, bool approved)
{
    const char *op=str(obj,"op");
    if (strcmp(op,"player_status")==0) return result(true,NULL);
    if (!approved) return result(false,"not joined to approved network");
    if (strcmp(op,"player_release")==0) {
        if (releasing || (!durable && !playing)) return result(true,NULL);
        bool manual=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(obj,"manual"));
        if (!playing || (!palette_mode && !retained_mode) || (!hue_takeover && !manual)) return result(false,"release requires active native playback");
        bool released=release_begin("hue_takeover");
        return result(released,released ? NULL : "could not persist release");
    }
    if (strcmp(op,"player_takeover")==0) {
        const cJSON *enabled=cJSON_GetObjectItemCaseSensitive(obj,"enabled");
        if (!cJSON_IsBool(enabled)) return result(false,"enabled must be boolean");
        bool value=cJSON_IsTrue(enabled);
        if (durable && (nvs_set_u8(store,"take",value)!=ESP_OK || nvs_commit(store)!=ESP_OK)) return result(false,"could not persist takeover option");
        hue_takeover=value;hue_deadline=now()+15000;return result(true,NULL);
    }
    if (strcmp(op,"player_keepalive")==0) {
        if (playing && hue_takeover && !releasing) hue_deadline=now()+10000;
        return result(true,NULL);
    }
    if (strcmp(op,"player_stop")==0) {
        if (releasing || !durable) return result(true,NULL);
        restore_begin("requested_stop",cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(obj,"off")));
        return result(true,NULL);
    }
    if (strcmp(op,"player_prepare")==0) {
        if (durable) return result(false,"restore current player session first");
        int initial_address=0;
        if (cJSON_HasObjectItem(obj,"address") && !number(obj,"address",1,0xfff7,&initial_address))
            return result(false,"invalid verified address");
        if (!parse_plan(obj)) return result(false,"invalid recovery plan");
        uint8_t pan[8]; esp_zb_get_extended_pan_id(pan);
        if (memcmp(pan,plan_pan,8)!=0) return result(false,"plan network mismatch");
        char *body=cJSON_PrintUnformatted(obj);
        esp_err_t err=body ? (strlen(body)<20000 ? nvs_set_str(store,"journal",body) : ESP_ERR_INVALID_SIZE) : ESP_ERR_NO_MEM;
        if (err==ESP_OK) err=nvs_set_u8(store,"off",0);
        bool takeover=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(obj,"hue_takeover"));
        if (err==ESP_OK) err=nvs_set_u8(store,"yield",0);
        if (err==ESP_OK) err=nvs_set_u8(store,"take",takeover);
        if (err==ESP_OK) err=nvs_set_u8(store,"played",0);
        if (err==ESP_OK) err=nvs_set_u8(store,"paint",0);
        if (err==ESP_OK) err=nvs_commit(store);
        free(body);
        if (err!=ESP_OK) return result(false,"could not persist recovery plan");
        free(samples); samples=NULL; sample_count=0;
        free(paint); paint=NULL; paint_count=0;
        durable=true;hue_takeover=takeover;releasing=playback_persisted=false;
        retained_mode=geometry_dirty=geometry_release=pending_paint=pending_paint_check=false;
        preserve_off=false; state="configuring"; reason="prepared"; armed_until=now()+120000;
        configuring=true; restoring=true; checking=false; step=0; pending=false; next_due=now();
        // The host just resolved this IEEE and verified identity, appearance
        // and geometry at this address before preparing ownership. The hint is
        // used only here; parse_plan() deliberately ignores it after reboot.
        resolved=initial_address!=0;
        if (resolved) address=(uint16_t)initial_address;
        resolving=false; retries=0; return result(true,NULL);
    }
    if (strcmp(op,"player_load")==0) {
        if (playing && retained_mode && geometry_dirty)
            return result(false,"wait until the current puck scene is applied");
        const cJSON *array=cJSON_GetObjectItemCaseSensitive(obj,"samples");
        int n=cJSON_GetArraySize(array), rate, period;
        const char *transport=str(obj,"transport");
        bool native=transport && strcmp(transport,"palette")==0;
        bool retained=transport && strcmp(transport,"retained")==0;
        if (native && cJSON_GetNumberValue(cJSON_GetObjectItemCaseSensitive(obj,"fps"))>10)
            return result(false,"native palette playback supports fps 1..10");
        if (transport && strcmp(transport,"palette") && strcmp(transport,"segments") && !retained)
            return result(false,"transport must be segments, palette or retained");
        if (!durable || restoring || (strcmp(state,"armed") && strcmp(state,"playing")) || !cJSON_IsArray(array) || n<1 || n>MAX_FRAMES || !number(obj,"fps",1,25,&rate))
            return result(false,"load requires armed player, 1..64 frames and fps 1..25");
        period=1000*n/rate;
        if (cJSON_HasObjectItem(obj,"cycle_ms") && !number(obj,"cycle_ms",80,600000,&period))
            return result(false,"cycle_ms must be 80..600000");
        sample_t *temp=calloc(n,sizeof(sample_t));
        if (!temp) return result(false,"out of memory");
        bool valid=true;
        for (int i=0;i<n;i++) {
            const cJSON *v=cJSON_GetArrayItem(array,i);
            int length=hm_unhex(cJSON_IsString(v)?v->valuestring:NULL,temp[i].data,HM_MAX_PAYLOAD);
            if (length<0 || (retained ? length!=6 : native ? !hm_palette_frame(temp[i].data,length) :
                (length<13 || (length-6)%7 || length>195))) { valid=false; break; }
            temp[i].length=length;
        }
        if (!valid) { free(temp); return result(false,"invalid segment/native palette frame"); }
        packet_t *program=NULL;size_t np=0;
        if (retained) {
            int positions;
            const cJSON *paint_array=cJSON_GetObjectItemCaseSensitive(obj,"paint");
            int steps=cJSON_GetArraySize(paint_array);
            if (steps>=5 && steps<=MAX_PAINT_STEPS) program=calloc(steps,sizeof(packet_t));
            valid=program && n==1 && number(obj,"positions",1,MAX_POSITIONS,&positions) &&
                packets(paint_array,program,steps,&np) &&
                retained_program(program,np,positions);
            if (!valid) {free(program);free(temp);return result(false,"invalid retained puck program");}
            free(paint);paint=program;paint_count=np;
        }
        if (!retained) {free(paint);paint=NULL;paint_count=0;}
        free(samples); samples=temp; sample_count=n; fps=rate; cycle_ms=period;
        palette_mode=native;retained_mode=retained;return result(true,NULL);
    }
    if (strcmp(op,"player_start")==0) {
        int ms;
        if (!durable || restoring || (strcmp(state,"armed") && strcmp(state,"playing")) || !samples || !number(obj,"duration_ms",0,86400000,&ms))
            return result(false,"prepare and load first; duration_ms 0 (until stopped) or <=86400000");
        bool was_playing=playing;
        if (retained_mode) {
            if (nvs_set_u8(store,"paint",1)!=ESP_OK || nvs_commit(store)!=ESP_OK)
                return result(false,"could not persist painting recovery");
            geometry_dirty=true;paint_step=paint_check_step=0;
            pending_paint=pending_paint_check=false;
        }
        hue_deadline=now()+15000;
        duration_ms=ms; started=now(); expires=ms ? started+ms : 0; playing=true;
        state="playing"; reason="requested_start"; next_due=started; retries=0; first_frame=ended=0; last_slot=-1; last_status=0;
        // Do not abandon an in-flight fragmented frame when a host changes scene.
        // Resynchronize the fixture at the next free slot before the new bank.
        if (!was_playing) {pending=false; pending_sync=false; counter=0;}
        sync_requested=!palette_mode && !retained_mode; bank_acked=false; pending_current_bank=false;
        frames_sent=pending ? 1 : 0; frames_acked=failures=skipped=0; last_power=0; last_power_reply=last_target_ack=started;
        animation_timeouts=0;failure_cause=failure_stage="none";failure_step=0;
        return result(true,NULL);
    }
    return result(false,"unknown player operation");
}
