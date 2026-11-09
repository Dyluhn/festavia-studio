// SPDX-License-Identifier: MIT
// Experimental router on an existing Hue network. Never forms a network.
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include "cJSON.h"
#include "esp_app_desc.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_zigbee_core.h"
#include "zboss_api.h"
#include "esp_zigbee_cluster.h"
#include "esp_zigbee_endpoint.h"
#include "esp_zigbee_attribute.h"
#include "esp_zigbee_secur.h"
#include "ha/esp_zigbee_ha_standard.h"
#include "aps/esp_zigbee_aps.h"
#include "nwk/esp_zigbee_nwk.h"
#include "zdo/esp_zigbee_zdo_command.h"
#include "wire.h"
#include "network.h"
#include "player.h"

#if !CONFIG_IDF_TARGET_ESP32C6 && !CONFIG_IDF_TARGET_ESP32H2
#error This firmware requires the native 802.15.4 radio in ESP32-C6 or ESP32-H2.
#endif
#if !CONFIG_ZB_ZCZR
#error Select CONFIG_ZB_ZCZR (router-capable Zigbee stack).
#endif

#define LAMP_EP 11
#define CLIENT_EP 20
#define READY_BIT BIT0
#define JOIN_LIMIT_MS 30000
#define RX_LIMIT 256

static EventGroupHandle_t ready;
static QueueHandle_t serial_output;
static uint32_t serial_dropped;
static nvs_handle_t settings;
// Zigbee state is protected by the ZB lock; the UART queue is RTOS-owned.
static bool network_up, have_expected, join_pending, scan_pending;
static uint8_t expected[8], saved_channel = 11, sequence;
static uint8_t saved_security; // 0: centralized Zigbee 3; 1: legacy ZLL distributed
static bool join_once;
static int scan_id;
static int64_t last_tx_us, zdo_until_us;
static int zdo_id = -1;
// SDK1.6.8 copies the ASDU synchronously into its own ZBOSS buffer. Keep the
// frame alive through that call, rather than gating future sends on callback
// correlation. The pinned SDK confirm callback also owns a separate ASDU copy.
static uint32_t tx_accepted, tx_confirmations;
static bool send_active;
static uint32_t confirms_during_send, confirms_without_header;
static uint32_t sdk_no_mem, rx_control_frames;

static unsigned sdk_free_buffers(void)
{
    zb_bufid_t held[128];
    unsigned count=0;
    while (count<128 && (held[count]=zb_buf_get_out())!=ZB_BUF_INVALID) count++;
    for (unsigned i=0;i<count;i++) zb_buf_free(held[i]);
    return count;
}

static void emit(cJSON *obj)
{
    if (!obj) return;
    char *json = cJSON_PrintUnformatted(obj);
    if (json) {
        const cJSON *id = cJSON_GetObjectItemCaseSensitive(obj, "id");
        hm_net_emit(json, cJSON_IsNumber(id) ? id->valueint : -1, cJSON_HasObjectItem(obj, "event"));
        // UART can block for tens of milliseconds. Never hold the Zigbee lock
        // while waiting for it; reserve queue space for command replies.
        bool is_event=cJSON_HasObjectItem(obj, "event");
        if ((is_event && uxQueueSpacesAvailable(serial_output)<4) ||
            xQueueSend(serial_output,&json,0)!=pdTRUE) {
            serial_dropped++;
            cJSON_free(json);
        }
    }
    cJSON_Delete(obj);
}

static cJSON *reply(int id, bool ok)
{
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddNumberToObject(obj, "id", id);
    cJSON_AddBoolToObject(obj, "ok", ok);
    return obj;
}

static cJSON *event(const char *name)
{
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddStringToObject(obj, "event", name);
    return obj;
}

static void error_reply(int id, const char *message)
{
    cJSON *obj = reply(id, false);
    cJSON_AddStringToObject(obj, "error", message);
    emit(obj);
}

static bool integer(const cJSON *obj, const char *key, int min, int max, int *out)
{
    cJSON *value = cJSON_GetObjectItemCaseSensitive(obj, key);
    if (!cJSON_IsNumber(value) || !isfinite(value->valuedouble) ||
        value->valuedouble < min || value->valuedouble > max ||
        value->valuedouble != (double)value->valueint) return false;
    *out = value->valueint;
    return true;
}

static const char *string(const cJSON *obj, const char *key)
{
    cJSON *value = cJSON_GetObjectItemCaseSensitive(obj, key);
    return cJSON_IsString(value) ? value->valuestring : NULL;
}

static bool approved_network(void)
{
    uint8_t actual[8];
    esp_zb_get_extended_pan_id(actual);
    return network_up && have_expected && memcmp(actual, expected, 8) == 0;
}

static void add_network(cJSON *obj)
{
    uint8_t addr[8];
    char hex[17];
    esp_zb_get_long_address(addr);
    hm_eui64_text(addr, hex);
    cJSON_AddStringToObject(obj, "ieee", hex);
    esp_zb_get_extended_pan_id(addr);
    hm_eui64_text(addr, hex);
    cJSON_AddStringToObject(obj, "extpan", hex);
    if (have_expected) {
        hm_eui64_text(expected, hex);
        cJSON_AddStringToObject(obj, "expected_extpan", hex);
    }
    cJSON_AddNumberToObject(obj, "channel", esp_zb_get_current_channel());
    cJSON_AddNumberToObject(obj, "pan", esp_zb_get_pan_id());
    cJSON_AddNumberToObject(obj, "address", esp_zb_get_short_address());
    cJSON_AddBoolToObject(obj, "network_up", network_up);
    cJSON_AddBoolToObject(obj, "approved_network", approved_network());
    cJSON_AddBoolToObject(obj, "factory_new", esp_zb_bdb_is_factory_new());
    cJSON_AddBoolToObject(obj, "joining", join_pending);
}

static void join_expired(uint8_t unused)
{
    (void)unused;
    if (!join_pending) return;
    esp_zb_bdb_cancel_steering();
    join_pending = false;
    cJSON *obj = event("join_timeout");
    add_network(obj);
    emit(obj);
}

static void restart_for_join(uint8_t unused)
{
    (void)unused;
    esp_restart();
}

void esp_zb_app_signal_handler(esp_zb_app_signal_t *signal)
{
    if (!signal || !signal->p_app_signal) return;
    uint32_t type = *signal->p_app_signal;
    esp_err_t status = signal->esp_err_status;
    if (type == ESP_ZB_ZDO_SIGNAL_SKIP_STARTUP) {
        ESP_ERROR_CHECK(esp_zb_bdb_start_top_level_commissioning(ESP_ZB_BDB_MODE_INITIALIZATION));
        return;
    }
    if (type == ESP_ZB_BDB_SIGNAL_DEVICE_FIRST_START || type == ESP_ZB_BDB_SIGNAL_DEVICE_REBOOT) {
        network_up = status == ESP_OK && !esp_zb_bdb_is_factory_new();
        if (join_once && status == ESP_OK && esp_zb_bdb_is_factory_new()) {
            join_once = false;
            join_pending = true;
            esp_err_t result = esp_zb_bdb_start_top_level_commissioning(ESP_ZB_BDB_MODE_NETWORK_STEERING);
            if (result == ESP_OK) esp_zb_scheduler_alarm(join_expired, 0, JOIN_LIMIT_MS);
            else join_pending = false;
        }
        xEventGroupSetBits(ready, READY_BIT);
    } else if (type == ESP_ZB_BDB_SIGNAL_STEERING) {
        network_up = status == ESP_OK;
        join_pending = false;
        esp_zb_scheduler_alarm_cancel(join_expired, 0);
    } else if (type == ESP_ZB_ZDO_SIGNAL_LEAVE) {
        network_up = false;
        join_pending = false;
    }
    cJSON *obj = event("network_signal");
    cJSON_AddStringToObject(obj, "signal", esp_zb_zdo_signal_to_string(type));
    cJSON_AddNumberToObject(obj, "status", status);
    add_network(obj);
    emit(obj);
}

static void scan_done(esp_zb_zdp_status_t status, uint8_t count, esp_zb_network_descriptor_t *networks)
{
    cJSON *obj = reply(scan_id, status == ESP_ZB_ZDP_STATUS_SUCCESS);
    cJSON_AddNumberToObject(obj, "status", status);
    cJSON *array = cJSON_AddArrayToObject(obj, "networks");
    for (int i = 0; networks && i < count; i++) {
        cJSON *net = cJSON_CreateObject();
        char hex[17];
        hm_eui64_text(networks[i].extended_pan_id, hex);
        cJSON_AddStringToObject(net, "extpan", hex);
        cJSON_AddNumberToObject(net, "pan", networks[i].short_pan_id);
        cJSON_AddNumberToObject(net, "channel", networks[i].logic_channel);
        cJSON_AddBoolToObject(net, "permit_join", networks[i].permit_joining);
        cJSON_AddBoolToObject(net, "router_capacity", networks[i].router_capacity);
        cJSON_AddItemToArray(array, net);
    }
    scan_pending = false;
    emit(obj);
}

static void zdo_finished(int id)
{
    if (zdo_id == id) zdo_id = -1;
}

static void resolve_done(esp_zb_zdp_status_t status, esp_zb_zdo_nwk_addr_rsp_t *response, void *ctx)
{
    int id = (int)(intptr_t)ctx;
    cJSON *obj = reply(id, status == ESP_ZB_ZDP_STATUS_SUCCESS && response);
    cJSON_AddNumberToObject(obj, "status", status);
    if (status == ESP_ZB_ZDP_STATUS_SUCCESS && response) {
        char hex[17];
        hm_eui64_text(response->ieee_addr, hex);
        cJSON_AddStringToObject(obj, "ieee", hex);
        cJSON_AddNumberToObject(obj, "address", response->nwk_addr);
    }
    zdo_finished(id);
    emit(obj);
}

static void endpoints_done(esp_zb_zdp_status_t status, uint8_t count, uint8_t *endpoints, void *ctx)
{
    int id = (int)(intptr_t)ctx;
    cJSON *obj = reply(id, status == ESP_ZB_ZDP_STATUS_SUCCESS);
    cJSON_AddNumberToObject(obj, "status", status);
    cJSON *array = cJSON_AddArrayToObject(obj, "endpoints");
    for (int i = 0; endpoints && i < count; i++) cJSON_AddItemToArray(array, cJSON_CreateNumber(endpoints[i]));
    zdo_finished(id);
    emit(obj);
}

static void descriptor_done(esp_zb_zdp_status_t status, esp_zb_af_simple_desc_1_1_t *desc, void *ctx)
{
    int id = (int)(intptr_t)ctx;
    cJSON *obj = reply(id, status == ESP_ZB_ZDP_STATUS_SUCCESS && desc);
    cJSON_AddNumberToObject(obj, "status", status);
    if (status == ESP_ZB_ZDP_STATUS_SUCCESS && desc) {
        cJSON_AddNumberToObject(obj, "endpoint", desc->endpoint);
        cJSON_AddNumberToObject(obj, "profile", desc->app_profile_id);
        cJSON_AddNumberToObject(obj, "device", desc->app_device_id);
        cJSON *in = cJSON_AddArrayToObject(obj, "input_clusters");
        cJSON *out = cJSON_AddArrayToObject(obj, "output_clusters");
        for (int i = 0; i < desc->app_input_cluster_count; i++)
            cJSON_AddItemToArray(in, cJSON_CreateNumber(desc->app_cluster_list[i]));
        for (int i = 0; i < desc->app_output_cluster_count; i++)
            cJSON_AddItemToArray(out, cJSON_CreateNumber(desc->app_cluster_list[desc->app_input_cluster_count + i]));
    }
    zdo_finished(id);
    emit(obj);
}

static bool aps_received(esp_zb_apsde_data_ind_t ind)
{
    // Capture only application ZCL, never key transport, ZDO, or security frames.
    if (ind.profile_id != 0x0104 || !ind.asdu) return false;
    bool control=ind.dst_endpoint==CLIENT_EP &&
        ind.dst_addr_mode==ESP_ZB_APS_ADDR_MODE_16_ENDP_PRESENT &&
        ind.dst_short_addr==esp_zb_get_short_address() &&
        ind.asdu_length>0 && (ind.asdu[0]&0x08);
    if (control) rx_control_frames++;
    if (ind.asdu_length>RX_LIMIT) return control;
    // A player reply has been consumed. Returning false would also hand it to
    // the SDK's ZCL dispatcher as an unhandled frame on the control endpoint.
    if (hm_player_receive(ind)) return true;
    cJSON *obj = event("zcl_rx");
    char hex[RX_LIMIT * 2 + 1];
    hm_hex(ind.asdu, ind.asdu_length, hex);
    cJSON_AddStringToObject(obj, "frame", hex);
    cJSON_AddNumberToObject(obj, "address", ind.src_short_addr);
    cJSON_AddNumberToObject(obj, "endpoint", ind.src_endpoint);
    cJSON_AddNumberToObject(obj, "dst_endpoint", ind.dst_endpoint);
    cJSON_AddNumberToObject(obj, "cluster", ind.cluster_id);
    cJSON_AddNumberToObject(obj, "lqi", ind.lqi);
    cJSON_AddNumberToObject(obj, "security", ind.security_status);
    uint8_t tsn, command;
    size_t header;
    if (hm_zcl_header(ind.asdu, ind.asdu_length, &tsn, &command, &header)) {
        cJSON_AddNumberToObject(obj, "sequence", tsn);
        cJSON_AddNumberToObject(obj, "command", command);
        cJSON_AddNumberToObject(obj, "frame_type", ind.asdu[0] & 3);
        cJSON_AddBoolToObject(obj, "server_to_client", (ind.asdu[0] & 8) != 0);
        cJSON_AddNumberToObject(obj, "manufacturer", (ind.asdu[0] & 4) ? ind.asdu[1] | ind.asdu[2] << 8 : -1);
        hm_hex(ind.asdu + header, ind.asdu_length - header, hex);
        cJSON_AddStringToObject(obj, "payload", hex);
    }
    emit(obj);
    // Own unicast replies belong to the host/player, including vendor replies
    // without a normal SDK transaction. Leave interviews, groups and the lamp
    // server to the stack instead of dispatching our replies a second time.
    return control;
}

unsigned hm_pending_transfers(void)
{
    return tx_accepted >= tx_confirmations ? tx_accepted - tx_confirmations : 0;
}

static void aps_confirmed(esp_zb_apsde_data_confirm_t confirm)
{
    if (confirm.src_endpoint != CLIENT_EP) return;
    if (send_active) confirms_during_send++;
    tx_confirmations++;
    bool handled=hm_player_confirm(confirm);
    uint8_t header_tsn,header_cmd;size_t header_size;
    if (!hm_zcl_header(confirm.asdu,confirm.asdu_length,&header_tsn,&header_cmd,&header_size))
        confirms_without_header++;
    if (handled) return;
    cJSON *obj = event("aps_confirm");
    cJSON_AddNumberToObject(obj, "status", confirm.status);
    cJSON_AddNumberToObject(obj, "address", confirm.dst_addr.addr_short);
    cJSON_AddNumberToObject(obj, "endpoint", confirm.dst_endpoint);
    uint8_t tsn, command;
    size_t header;
    if (hm_zcl_header(confirm.asdu, confirm.asdu_length, &tsn, &command, &header))
        cJSON_AddNumberToObject(obj, "sequence", tsn);
    emit(obj);
}

static esp_err_t core_action(esp_zb_core_action_callback_id_t action, const void *message)
{
    if (action == ESP_ZB_CORE_SET_ATTR_VALUE_CB_ID && message) {
        const esp_zb_zcl_set_attr_value_message_t *attr = message;
        cJSON *obj = event("test_lamp_attribute");
        cJSON_AddNumberToObject(obj, "cluster", attr->info.cluster);
        cJSON_AddNumberToObject(obj, "attribute", attr->attribute.id);
        cJSON_AddNumberToObject(obj, "status", attr->info.status);
        emit(obj);
    }
    return ESP_OK;
}

static esp_err_t save_network(void)
{
    esp_err_t err = nvs_set_blob(settings, "expected", expected, sizeof(expected));
    if (err == ESP_OK) err = nvs_set_u8(settings, "channel", saved_channel);
    if (err == ESP_OK) err = nvs_set_u8(settings, "security", saved_security);
    if (err == ESP_OK) err = nvs_commit(settings);
    return err;
}

static void set_security(uint8_t mode)
{
    // The published ZLL commissioning key is protocol material, not a recovered
    // household network key. Centralized mode retains the SDK's default TC key.
    static uint8_t zll_key[16] = {0x81,0x42,0x86,0x86,0x5d,0xc1,0xc8,0xb2,
                                  0xc8,0xcb,0xc5,0x2e,0x5d,0x65,0xd1,0xb8};
    esp_zb_enable_joining_to_distributed(mode == 1);
    if (mode == 1) esp_zb_secur_TC_standard_distributed_key_set(zll_key);
}

static esp_err_t send_frame(uint16_t address, uint8_t endpoint, uint16_t cluster,
                  bool specific, int manufacturer, uint8_t command,
                  const uint8_t *payload, size_t size, bool quiet, bool acknowledged, uint8_t *tsn)
{
    *tsn=sequence++;
    uint8_t frame[HM_MAX_FRAME];
    size_t length=hm_frame(frame,specific,manufacturer,*tsn,command,payload,size);
    if (!length) return ESP_ERR_INVALID_ARG;
    if (quiet) frame[0] |= 0x10;
    esp_zb_apsde_data_req_t req={
        .dst_addr_mode=ESP_ZB_APS_ADDR_MODE_16_ENDP_PRESENT,
        .dst_addr.addr_short=address, .dst_endpoint=endpoint,
        .src_endpoint=CLIENT_EP, .profile_id=0x0104, .cluster_id=cluster,
        .asdu=frame, .asdu_length=length,
        .tx_options=(acknowledged ? ESP_ZB_APSDE_TX_OPT_ACK_TX | ESP_ZB_APSDE_TX_OPT_FRAG_PERMITTED : 0) | ESP_ZB_APSDE_TX_OPT_NO_LONG_ADDR, .radius=30,
    };
    send_active=true;
    esp_err_t result=esp_zb_aps_data_request(&req);
    send_active=false;
    if (result==ESP_ERR_NO_MEM) sdk_no_mem++;
    if (result==ESP_OK) tx_accepted++;
    return result;
}

esp_err_t hm_send(uint16_t address, uint8_t endpoint, uint16_t cluster,
                  bool specific, int manufacturer, uint8_t command,
                  const uint8_t *payload, size_t size, bool quiet, uint8_t *tsn)
{
    return send_frame(address,endpoint,cluster,specific,manufacturer,command,payload,size,quiet,true,tsn);
}

esp_err_t hm_send_animation(uint16_t address, uint8_t endpoint,
                           const uint8_t *payload, size_t size, uint8_t *tsn)
{
    // Native frames fit one radio payload and supersede earlier colors. Keep
    // normal unicast/MAC delivery while avoiding APS retries of stale frames.
    if (!hm_palette_frame(payload,size)) return ESP_ERR_INVALID_ARG;
    return send_frame(address,endpoint,0xfc03,true,0x100b,0,payload,size,true,false,tsn);
}

static void handle_request(cJSON *request)
{
    int id;
    if (!integer(request, "id", 1, 0x7fffffff, &id)) {
        error_reply(0, "id must be an integer in 1..2147483647");
        return;
    }
    const char *op = string(request, "op");
    if (!op) { error_reply(id, "missing op"); return; }
    if (strncmp(op,"player_",7)==0) {
        cJSON *obj=hm_player_command(request,approved_network());
        cJSON_AddNumberToObject(obj,"id",id); emit(obj); return;
    }
    if (strcmp(op, "status") == 0) {
        cJSON *obj = reply(id, true);
        cJSON_AddStringToObject(obj, "firmware", "hue-mesh-lab");
        cJSON_AddStringToObject(obj, "version", esp_app_get_description()->version);
        cJSON_AddStringToObject(obj, "target", CONFIG_IDF_TARGET);
        cJSON_AddNumberToObject(obj, "protocol", 1);
        cJSON_AddNumberToObject(obj, "free_heap", esp_get_free_heap_size());
        cJSON_AddNumberToObject(obj, "uptime_ms", esp_timer_get_time()/1000);
        cJSON_AddNumberToObject(obj, "sdk_buffers_free", sdk_free_buffers());
        cJSON_AddNumberToObject(obj, "sdk_buffer_probe_limit", 128);
        cJSON_AddNumberToObject(obj, "sdk_no_mem", sdk_no_mem);
        cJSON_AddNumberToObject(obj, "serial_dropped", serial_dropped);
        cJSON_AddNumberToObject(obj, "app_tx_pool_full", 0);
        cJSON_AddNumberToObject(obj, "tx_accepted", tx_accepted);
        cJSON_AddNumberToObject(obj, "tx_confirmations", tx_confirmations);
        cJSON_AddNumberToObject(obj, "rx_control_frames", rx_control_frames);
        cJSON_AddNumberToObject(obj, "aps_confirms_during_send", confirms_during_send);
        cJSON_AddNumberToObject(obj, "aps_confirms_without_header", confirms_without_header);
        cJSON_AddNumberToObject(obj, "outbound_in_use", hm_pending_transfers());
        cJSON_AddNumberToObject(obj, "lamp_endpoint", LAMP_EP);
        cJSON_AddNumberToObject(obj, "client_endpoint", CLIENT_EP);
        add_network(obj);
        hm_net_info(obj);
        emit(obj);
        return;
    }
    if (strcmp(op, "net_info") == 0) {
        cJSON *obj = reply(id, true);
        hm_net_info(obj);
        emit(obj);
        return;
    }
    if (strcmp(op, "net_config") == 0) {
        esp_err_t result = hm_net_configure(request);
        cJSON *obj = reply(id, result == ESP_OK);
        cJSON_AddStringToObject(obj, "result", esp_err_to_name(result));
        hm_net_info(obj);
        emit(obj);
        return;
    }
    if (hm_player_busy() && (strcmp(op,"join")==0 || strcmp(op,"forget")==0)) {
        error_reply(id,"stop and recover playback before changing network membership"); return;
    }
    if (strcmp(op, "scan") == 0) {
        if (scan_pending || join_pending || network_up) {
            error_reply(id, "scan requires an idle unjoined device"); return;
        }
        int channel = 0;
        if (cJSON_HasObjectItem(request, "channel") && !integer(request, "channel", 11, 26, &channel)) {
            error_reply(id, "channel must be 11..26"); return;
        }
        scan_pending = true;
        scan_id = id;
        esp_zb_zdo_active_scan_request(channel ? 1UL << channel : ESP_ZB_TRANSCEIVER_ALL_CHANNELS_MASK, 3, scan_done);
        return;
    }
    if (strcmp(op, "join") == 0) {
        uint8_t requested[8];
        int channel, security;
        if (!hm_eui64(string(request, "extpan"), requested) ||
            !integer(request, "channel", 11, 26, &channel) ||
            !integer(request, "security", 0, 1, &security)) {
            error_reply(id, "join needs extpan (16 hex digits), channel (11..26), security (0=z3,1=zll)"); return;
        }
        if (scan_pending || join_pending) { error_reply(id, "commissioning already active"); return; }
        uint8_t actual[8];
        esp_zb_get_extended_pan_id(actual);
        if (!esp_zb_bdb_is_factory_new() && memcmp(actual, requested, 8) != 0) {
            error_reply(id, "already paired to another network; forget this ESP32 first"); return;
        }
        memcpy(expected, requested, 8);
        saved_channel = channel;
        saved_security = security;
        have_expected = save_network() == ESP_OK;
        if (!have_expected) { error_reply(id, "could not persist network selection"); return; }
        esp_err_t result = ESP_OK;
        if (esp_zb_bdb_is_factory_new()) {
            // Extended PAN selection must be configured before esp_zb_start.
            // Persist one explicit attempt; consume it before stack startup so
            // a power cycle after a failed attempt cannot restart commissioning.
            result = nvs_set_u8(settings, "join_once", 1);
            if (result == ESP_OK) result = nvs_commit(settings);
            if (result == ESP_OK) {
                join_pending = true;
                esp_zb_scheduler_alarm(restart_for_join, 0, 250);
            }
        }
        cJSON *obj = reply(id, result == ESP_OK);
        cJSON_AddStringToObject(obj, "result", esp_err_to_name(result));
        cJSON_AddBoolToObject(obj, "restarting", join_pending);
        add_network(obj);
        emit(obj);
        return;
    }
    if (strcmp(op, "forget") == 0) {
        // This resets only this ESP32's network/settings; never a remote lamp.
        nvs_erase_all(settings);
        ESP_ERROR_CHECK(nvs_commit(settings));
        emit(reply(id, true));
        esp_zb_factory_reset();
        return;
    }
    if (!approved_network()) { error_reply(id, "not joined to the selected network"); return; }
    if (strcmp(op, "resolve") == 0 || strcmp(op, "endpoints") == 0 || strcmp(op, "descriptor") == 0) {
        if (zdo_id >= 0 && esp_timer_get_time() < zdo_until_us) {
            error_reply(id, "another ZDO request is pending"); return;
        }
        int address, endpoint;
        // Address discovery is broadcast to awake nodes so the target can
        // answer for itself; a coordinator need not proxy a lamp's address.
        // This is a read-only ZDO query, never a broadcast lighting command.
        esp_zb_zdo_nwk_addr_req_param_t req = {.dst_nwk_addr = 0xfffd, .request_type = 0};
        if (strcmp(op, "resolve") == 0) {
            if (!hm_eui64(string(request, "ieee"), req.ieee_addr_of_interest)) {
                error_reply(id, "ieee must be 16 hex digits"); return;
            }
        } else if (!integer(request, "address", 1, 0xfff7, &address)) {
            error_reply(id, "address must be a unicast lamp address"); return;
        } else if (strcmp(op, "descriptor") == 0 && !integer(request, "endpoint", 1, 240, &endpoint)) {
            error_reply(id, "endpoint must be 1..240"); return;
        }
        zdo_id = id;
        zdo_until_us = esp_timer_get_time() + 20000000;
        if (strcmp(op, "resolve") == 0) esp_zb_zdo_nwk_addr_req(&req, resolve_done, (void *)(intptr_t)id);
        else if (strcmp(op, "endpoints") == 0) {
            esp_zb_zdo_active_ep_req_param_t req = {.addr_of_interest = address};
            esp_zb_zdo_active_ep_req(&req, endpoints_done, (void *)(intptr_t)id);
        } else {
            esp_zb_zdo_simple_desc_req_param_t req = {.addr_of_interest = address, .endpoint = endpoint};
            esp_zb_zdo_simple_desc_req(&req, descriptor_done, (void *)(intptr_t)id);
        }
        return;
    }
    if (strcmp(op, "tx") == 0) {
        int address, endpoint, cluster, type, manufacturer, command;
        uint8_t payload[HM_MAX_PAYLOAD], frame[HM_MAX_FRAME];
        int size = hm_unhex(string(request, "payload"), payload, sizeof(payload));
        if (!integer(request, "address", 1, 0xfff7, &address) ||
            !integer(request, "endpoint", 1, 240, &endpoint) ||
            !integer(request, "cluster", 0, 65535, &cluster) ||
            !integer(request, "frame_type", 0, 1, &type) ||
            !integer(request, "manufacturer", -1, 65535, &manufacturer) ||
            !integer(request, "command", 0, 255, &command) || size < 0 ||
            !hm_unicast(address, endpoint)) {
            error_reply(id, "invalid tx parameters (256 payload bytes maximum)"); return;
        }
        if (hm_player_busy() && !(type==0 && command==0) &&
            !(cluster==0xfc01 && (command==4 || command==6))) {
            error_reply(id,"on-device player owns writes; use player_stop first"); return;
        }
        if (esp_timer_get_time() - last_tx_us < 100000) {
            error_reply(id, "tx rate limit: wait at least 100ms"); return;
        }
        uint8_t tsn;
        esp_err_t result = hm_send(address,endpoint,cluster,type==1,manufacturer,command,payload,size,false,&tsn);
        size_t length=hm_frame(frame,type==1,manufacturer,tsn,command,payload,size);
        last_tx_us = esp_timer_get_time();
        cJSON *obj = reply(id, result == ESP_OK);
        cJSON_AddStringToObject(obj, "result", esp_err_to_name(result));
        cJSON_AddNumberToObject(obj, "sequence", tsn);
        char hex[HM_MAX_FRAME * 2 + 1];
        hm_hex(frame, length, hex);
        cJSON_AddStringToObject(obj, "frame", hex);
        cJSON_AddStringToObject(obj, "meaning", "queued locally; await APS/ZCL response");
        emit(obj);
        return;
    }
    error_reply(id, "unknown op");
}

void hm_dispatch(cJSON *request)
{
    if (!(xEventGroupGetBits(ready) & READY_BIT)) return;
    esp_zb_lock_acquire(portMAX_DELAY);
    handle_request(request);
    esp_zb_lock_release();
}

static void zigbee_task(void *unused)
{
    (void)unused;
    esp_zb_cfg_t config = {
        .esp_zb_role = ESP_ZB_DEVICE_TYPE_ROUTER, .install_code_policy = false,
        .nwk_cfg.zczr_cfg.max_children = 0,
    };
    esp_zb_init(&config);
    set_security(saved_security);
    esp_zb_set_primary_network_channel_set(have_expected ? 1UL << saved_channel : ESP_ZB_TRANSCEIVER_ALL_CHANNELS_MASK);
    esp_zb_set_secondary_network_channel_set(0);
    if (have_expected) esp_zb_set_extended_pan_id(expected);

    // A plainly named virtual light for third-party Hue discovery. No GPIOs or
    // physical lights are driven by server-side commands to this endpoint.
    esp_zb_on_off_light_cfg_t lamp_cfg = ESP_ZB_DEFAULT_ON_OFF_LIGHT_CONFIG();
    esp_zb_ep_list_t *endpoints = esp_zb_on_off_light_ep_create(LAMP_EP, &lamp_cfg);
    esp_zb_attribute_list_t *basic = esp_zb_cluster_list_get_cluster(
        esp_zb_ep_list_get_ep(endpoints, LAMP_EP), ESP_ZB_ZCL_CLUSTER_ID_BASIC, ESP_ZB_ZCL_CLUSTER_SERVER_ROLE);
    static char manufacturer[] = "\x0a" "Dylan Labs";
    static char model[] = "\x0c" "Hue Mesh Lab";
    static char build[] = "\x05" "0.3.7";
    ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic, ESP_ZB_ZCL_ATTR_BASIC_MANUFACTURER_NAME_ID, manufacturer));
    ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic, ESP_ZB_ZCL_ATTR_BASIC_MODEL_IDENTIFIER_ID, model));
    ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic, ESP_ZB_ZCL_ATTR_BASIC_SW_BUILD_ID, build));

    esp_zb_cluster_list_t *clients = esp_zb_zcl_cluster_list_create();
    #define ADD_CLIENT(id, name) ESP_ERROR_CHECK(esp_zb_cluster_list_add_##name##_cluster( \
        clients, esp_zb_zcl_attr_list_create(id), ESP_ZB_ZCL_CLUSTER_CLIENT_ROLE))
    ADD_CLIENT(0x0000, basic);
    ADD_CLIENT(0x0003, identify);
    ADD_CLIENT(0x0004, groups);
    ADD_CLIENT(0x0005, scenes);
    ADD_CLIENT(0x0006, on_off);
    ADD_CLIENT(0x0008, level);
    ADD_CLIENT(0x0300, color_control);
    #undef ADD_CLIENT
    const uint16_t vendor_clusters[] = {0xfc01,0xfc03,0xfc04};
    for (size_t i = 0; i < sizeof(vendor_clusters) / sizeof(vendor_clusters[0]); i++) {
        esp_zb_attribute_list_t *list = esp_zb_zcl_attr_list_create(vendor_clusters[i]);
        ESP_ERROR_CHECK(esp_zb_cluster_list_add_custom_cluster(clients, list, ESP_ZB_ZCL_CLUSTER_CLIENT_ROLE));
    }
    esp_zb_endpoint_config_t client = {
        .endpoint = CLIENT_EP, .app_profile_id = 0x0104,
        .app_device_id = 0x0000, .app_device_version = 1,
    };
    ESP_ERROR_CHECK(esp_zb_ep_list_add_ep(endpoints, clients, client));
    ESP_ERROR_CHECK(esp_zb_device_register(endpoints));
    esp_zb_core_action_handler_register(core_action);
    esp_zb_aps_data_indication_handler_register(aps_received);
    esp_zb_aps_data_confirm_handler_register(aps_confirmed);
    ESP_ERROR_CHECK(esp_zb_start(false));
    esp_zb_stack_main_loop();
    vTaskDelete(NULL);
}

static void serial_task(void *unused)
{
    (void)unused;
    char *json;
    for (;;) if (xQueueReceive(serial_output,&json,portMAX_DELAY)==pdTRUE) {
        puts(json);
        fflush(stdout);
        cJSON_free(json);
    }
}

static void player_task(void *unused)
{
    (void)unused;
    xEventGroupWaitBits(ready,READY_BIT,pdFALSE,pdTRUE,portMAX_DELAY);
    for (;;) {
        esp_zb_lock_acquire(portMAX_DELAY);
        hm_player_tick(approved_network());
        esp_zb_lock_release();
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

void app_main(void)
{
    // Do not auto-erase NVS on errors: it may hold an existing network pairing.
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(nvs_open("hue_mesh_lab", NVS_READWRITE, &settings));
    hm_player_init();
    size_t length = sizeof(expected);
    have_expected = nvs_get_blob(settings, "expected", expected, &length) == ESP_OK && length == 8;
    nvs_get_u8(settings, "channel", &saved_channel);
    nvs_get_u8(settings, "security", &saved_security);
    if (saved_channel < 11 || saved_channel > 26 || saved_security > 1) have_expected = false;
    uint8_t pending = 0;
    nvs_get_u8(settings, "join_once", &pending);
    join_once = pending == 1 && have_expected;
    if (pending) {
        ESP_ERROR_CHECK(nvs_set_u8(settings, "join_once", 0));
        ESP_ERROR_CHECK(nvs_commit(settings));
    }
    ready = xEventGroupCreate();
    serial_output = xQueueCreate(16,sizeof(char *));
    configASSERT(ready && serial_output);
    configASSERT(xTaskCreate(serial_task,"serial_output",4096,NULL,3,NULL)==pdPASS);
    setvbuf(stdin, NULL, _IONBF, 0);
    setvbuf(stdout, NULL, _IONBF, 0);
    ESP_ERROR_CHECK(hm_net_init());
    esp_zb_platform_config_t platform = {
        .radio_config = {.radio_mode = ZB_RADIO_MODE_NATIVE},
        .host_config = {.host_connection_mode = ZB_HOST_CONNECTION_MODE_NONE},
    };
    ESP_ERROR_CHECK(esp_zb_platform_config(&platform));
    configASSERT(xTaskCreate(zigbee_task, "zigbee", 8192, NULL, 5, NULL) == pdPASS);
    configASSERT(xTaskCreate(player_task,"player",6144,NULL,4,NULL)==pdPASS);
    xEventGroupWaitBits(ready, READY_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
    ESP_ERROR_CHECK(hm_net_start());
    emit(event("ready"));

    // Consume a whole line before parsing, including oversized malformed lines.
    // fgets() fragments must never become separate commands.
    char line[1024];
    size_t used = 0;
    bool overflow = false;
    while (true) {
        int ch = getchar();
        if (ch == EOF) { clearerr(stdin); vTaskDelay(pdMS_TO_TICKS(10)); continue; }
        if (ch == '\r') continue;
        if (ch != '\n') {
            if (used < sizeof(line) - 1) line[used++] = ch;
            else overflow = true;
            continue;
        }
        line[used] = 0;
        if (overflow) error_reply(0, "line exceeds 1023 bytes");
        else if (used) {
            const char *end = NULL;
            cJSON *request = cJSON_ParseWithOpts(line, &end, true);
            if (!cJSON_IsObject(request)) error_reply(0, "invalid JSON object");
            else {
                hm_dispatch(request);
            }
            cJSON_Delete(request);
        }
        used = 0;
        overflow = false;
    }
}
