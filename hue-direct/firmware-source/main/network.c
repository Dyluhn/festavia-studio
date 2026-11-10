// SPDX-License-Identifier: MIT
#include "network.h"
#include "sdkconfig.h"

#if CONFIG_IDF_TARGET_ESP32C6
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_app_desc.h"
#include "esp_coexist.h"
#include "esp_event.h"
#include "esp_https_server.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_ota_ops.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "bootloader_random.h"
#include "nvs.h"
#include "mbedtls/ctr_drbg.h"
#include "mbedtls/entropy.h"
#include "mbedtls/pk.h"
#include "mbedtls/sha256.h"
#include "mbedtls/x509_crt.h"
#include "wire.h"

#define EVENTS 8
#define VERIFY_SECONDS 90
typedef struct { uint32_t sequence; char *json; } event_item_t;
typedef struct { int id; char *json; } reply_item_t;
static nvs_handle_t storage;
static esp_netif_t *station;
static httpd_handle_t server;
static SemaphoreHandle_t ring_mutex, request_mutex;
static QueueHandle_t replies;
static atomic_int remote_id;
static int next_id = 2100000000;
static event_item_t ring[EVENTS];
static uint32_t event_sequence;
static char cert[1536], key[512], fingerprint[65], api_token[65], hostname[24];
static atomic_bool configured, pending_verify;
static bool wifi_started;
static esp_timer_handle_t rollback_timer, restart_timer;

static bool token_valid(const char *text)
{
    uint8_t decoded[32];
    return text && strlen(text) == 64 && hm_unhex(text, decoded, 32) == 32;
}

static void restart(void *unused)
{
    (void)unused;
    esp_restart();
}

static esp_err_t certificate(void)
{
    size_t cert_len = sizeof(cert), key_len = sizeof(key);
    esp_err_t have_cert = nvs_get_str(storage, "cert", cert, &cert_len);
    esp_err_t have_key = nvs_get_str(storage, "key", key, &key_len);
    if (have_cert == ESP_ERR_NVS_NOT_FOUND && have_key == ESP_ERR_NVS_NOT_FOUND) {
        int err = 0;
        mbedtls_entropy_context entropy;
        mbedtls_ctr_drbg_context rng;
        mbedtls_pk_context pk;
        mbedtls_x509write_cert writer;
        mbedtls_entropy_init(&entropy);
        mbedtls_ctr_drbg_init(&rng);
        mbedtls_pk_init(&pk);
        mbedtls_x509write_crt_init(&writer);
        // Run before either RF stack starts, while the ADC entropy source can
        // be enabled safely. Never ship a shared TLS private key in the binary.
        bootloader_random_enable();
        #define TLS_CHECK(call) do { if ((err = (call)) != 0) goto cert_done; } while (0)
        const unsigned char personalization[] = "hue-mesh-device-tls";
        TLS_CHECK(mbedtls_ctr_drbg_seed(&rng, mbedtls_entropy_func, &entropy, personalization, sizeof(personalization)));
        TLS_CHECK(mbedtls_pk_setup(&pk, mbedtls_pk_info_from_type(MBEDTLS_PK_ECKEY)));
        TLS_CHECK(mbedtls_ecp_gen_key(MBEDTLS_ECP_DP_SECP256R1, mbedtls_pk_ec(pk), mbedtls_ctr_drbg_random, &rng));
        mbedtls_x509write_crt_set_version(&writer, MBEDTLS_X509_CRT_VERSION_3);
        mbedtls_x509write_crt_set_md_alg(&writer, MBEDTLS_MD_SHA256);
        mbedtls_x509write_crt_set_subject_key(&writer, &pk);
        mbedtls_x509write_crt_set_issuer_key(&writer, &pk);
        TLS_CHECK(mbedtls_x509write_crt_set_subject_name(&writer, "CN=Hue Mesh Lab"));
        TLS_CHECK(mbedtls_x509write_crt_set_issuer_name(&writer, "CN=Hue Mesh Lab"));
        uint8_t serial_bytes[16];
        esp_fill_random(serial_bytes, sizeof(serial_bytes));
        serial_bytes[0] &= 0x7f;
        serial_bytes[15] |= 1;
        TLS_CHECK(mbedtls_x509write_crt_set_serial_raw(&writer, serial_bytes, sizeof(serial_bytes)));
        TLS_CHECK(mbedtls_x509write_crt_set_validity(&writer, "20260101000000", "20560101000000"));
        TLS_CHECK(mbedtls_x509write_crt_set_basic_constraints(&writer, 0, -1));
        TLS_CHECK(mbedtls_x509write_crt_set_key_usage(&writer, MBEDTLS_X509_KU_DIGITAL_SIGNATURE));
        TLS_CHECK(mbedtls_x509write_crt_pem(&writer, (unsigned char *)cert, sizeof(cert), mbedtls_ctr_drbg_random, &rng));
        TLS_CHECK(mbedtls_pk_write_key_pem(&pk, (unsigned char *)key, sizeof(key)));
cert_done:
        bootloader_random_disable();
        mbedtls_x509write_crt_free(&writer);
        mbedtls_pk_free(&pk);
        mbedtls_ctr_drbg_free(&rng);
        mbedtls_entropy_free(&entropy);
        #undef TLS_CHECK
        if (err) return ESP_FAIL;
        if (nvs_set_str(storage, "cert", cert) != ESP_OK || nvs_set_str(storage, "key", key) != ESP_OK || nvs_commit(storage) != ESP_OK) return ESP_FAIL;
    } else if (have_cert != ESP_OK || have_key != ESP_OK) return ESP_FAIL;
    mbedtls_x509_crt parsed;
    uint8_t digest[32];
    mbedtls_x509_crt_init(&parsed);
    int err = mbedtls_x509_crt_parse(&parsed, (const unsigned char *)cert, strlen(cert) + 1);
    if (!err) err = mbedtls_sha256(parsed.raw.p, parsed.raw.len, digest, 0);
    if (!err) hm_hex(digest, sizeof(digest), fingerprint);
    mbedtls_x509_crt_free(&parsed);
    return err ? ESP_FAIL : ESP_OK;
}

void hm_net_emit(const char *json, int id, bool is_event)
{
    if (!replies) return;
    if (id > 0 && id == atomic_load(&remote_id)) {
        reply_item_t item = {.id = id, .json = strdup(json)};
        if (item.json && xQueueSend(replies, &item, 0) != pdTRUE) free(item.json);
    }
    if (is_event) {
        char *copy = strdup(json);
        if (!copy) return;
        xSemaphoreTake(ring_mutex, portMAX_DELAY);
        uint32_t seq = ++event_sequence;
        event_item_t *item = &ring[seq % EVENTS];
        free(item->json);
        item->sequence = seq;
        item->json = copy;
        xSemaphoreGive(ring_mutex);
    }
}

void hm_net_info(cJSON *object)
{
    cJSON *net = cJSON_AddObjectToObject(object, "network");
    cJSON_AddBoolToObject(net, "supported", true);
    cJSON_AddBoolToObject(net, "configured", configured);
    cJSON_AddStringToObject(net, "tls_sha256", fingerprint);
    cJSON_AddStringToObject(net, "hostname", hostname);
    cJSON_AddBoolToObject(net, "ota", true);
    cJSON_AddBoolToObject(net, "pending_verify", pending_verify);
    cJSON_AddNumberToObject(net, "verify_seconds", VERIFY_SECONDS);
    char elf[65];
    // The IDF convenience string is truncated to CONFIG_APP_RETRIEVE_LEN_ELF_SHA.
    // OTA confirmation needs all 32 bytes, regardless of the log setting.
    hm_hex(esp_app_get_description()->app_elf_sha256, 32, elf);
    cJSON_AddStringToObject(net, "elf_sha256", elf);
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (running) cJSON_AddStringToObject(net, "running_partition", running->label);
    if (station) {
        esp_netif_ip_info_t ip;
        if (esp_netif_get_ip_info(station, &ip) == ESP_OK && ip.ip.addr) {
            char address[16], url[32];
            snprintf(address, sizeof(address), IPSTR, IP2STR(&ip.ip));
            snprintf(url, sizeof(url), "https://%s", address);
            cJSON_AddStringToObject(net, "address", address);
            cJSON_AddStringToObject(net, "url", url);
        }
    }
}

static esp_err_t json_response(httpd_req_t *req, cJSON *object)
{
    char *body = cJSON_PrintUnformatted(object);
    cJSON_Delete(object);
    if (!body) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "out of memory");
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t result = httpd_resp_sendstr(req, body);
    free(body);
    return result;
}

static bool authorized(httpd_req_t *req)
{
    char value[80];
    size_t length = httpd_req_get_hdr_value_len(req, "Authorization");
    if (!configured || length != 71 || httpd_req_get_hdr_value_str(req, "Authorization", value, sizeof(value)) != ESP_OK) return false;
    unsigned difference = 0;
    const char prefix[] = "Bearer ";
    for (int i = 0; i < 7; i++) difference |= (unsigned char)value[i] ^ (unsigned char)prefix[i];
    for (int i = 0; i < 64; i++) difference |= (unsigned char)value[i + 7] ^ (unsigned char)api_token[i];
    return difference == 0;
}

static bool require_auth(httpd_req_t *req)
{
    if (authorized(req)) return true;
    httpd_resp_send_err(req, HTTPD_401_UNAUTHORIZED, "authentication required");
    return false;
}

static cJSON *read_json(httpd_req_t *req)
{
    if (req->content_len <= 0 || req->content_len > 40000) return NULL;
    char *body = malloc(req->content_len + 1);
    if (!body) return NULL;
    int read = 0;
    while (read < req->content_len) {
        int count = httpd_req_recv(req, body + read, req->content_len - read);
        if (count <= 0) { free(body); return NULL; }
        read += count;
    }
    body[read] = 0;
    cJSON *obj = cJSON_ParseWithOpts(body, NULL, true);
    free(body);
    if (!cJSON_IsObject(obj)) { cJSON_Delete(obj); return NULL; }
    return obj;
}

static esp_err_t command_response(httpd_req_t *req, cJSON *command)
{
    const cJSON *op = cJSON_GetObjectItemCaseSensitive(command, "op");
    if (!cJSON_IsString(op) || strcmp(op->valuestring, "net_config") == 0) {
        cJSON_Delete(command);
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid operation; Wi-Fi provisioning uses USB");
    }
    if (xSemaphoreTake(request_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        cJSON_Delete(command);
        httpd_resp_set_status(req, "503 Service Unavailable");
        return httpd_resp_sendstr(req, "command busy");
    }
    reply_item_t item;
    while (xQueueReceive(replies, &item, 0) == pdTRUE) free(item.json);
    int id = ++next_id;
    if (next_id >= 2140000000) next_id = 2100000000;
    cJSON *original = cJSON_GetObjectItemCaseSensitive(command, "id");
    int original_id = cJSON_IsNumber(original) ? original->valueint : 0;
    cJSON_DeleteItemFromObjectCaseSensitive(command, "id");
    cJSON_AddNumberToObject(command, "id", id);
    atomic_store(&remote_id, id);
    hm_dispatch(command);
    cJSON_Delete(command);
    TickType_t started = xTaskGetTickCount();
    cJSON *response = NULL;
    while ((xTaskGetTickCount() - started) < pdMS_TO_TICKS(20000)) {
        if (xQueueReceive(replies, &item, pdMS_TO_TICKS(100)) != pdTRUE) continue;
        if (item.id == id) response = cJSON_Parse(item.json);
        free(item.json);
        if (response) break;
    }
    atomic_store(&remote_id, 0);
    xSemaphoreGive(request_mutex);
    if (!response) return httpd_resp_send_err(req, HTTPD_408_REQ_TIMEOUT, "command timed out; effect is unconfirmed");
    cJSON_ReplaceItemInObjectCaseSensitive(response, "id", cJSON_CreateNumber(original_id));
    return json_response(req, response);
}

static esp_err_t status_handler(httpd_req_t *req)
{
    if (!require_auth(req)) return ESP_FAIL;
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddStringToObject(obj, "op", "status");
    return command_response(req, obj);
}

static esp_err_t command_handler(httpd_req_t *req)
{
    if (!require_auth(req)) return ESP_FAIL;
    cJSON *obj = read_json(req);
    if (!obj) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "invalid JSON object");
    return command_response(req, obj);
}

static esp_err_t events_handler(httpd_req_t *req)
{
    if (!require_auth(req)) return ESP_FAIL;
    char query[48], after_text[16];
    uint32_t after = 0;
    if (httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK &&
        httpd_query_key_value(query, "after", after_text, sizeof(after_text)) == ESP_OK)
        after = strtoul(after_text, NULL, 10);
    cJSON *obj = cJSON_CreateObject();
    cJSON *list = cJSON_AddArrayToObject(obj, "events");
    xSemaphoreTake(ring_mutex, portMAX_DELAY);
    uint32_t latest = event_sequence;
    uint32_t first = latest >= EVENTS ? latest - EVENTS + 1 : 1;
    cJSON_AddNumberToObject(obj, "cursor", latest);
    cJSON_AddBoolToObject(obj, "lost", after != 0 && after < first - 1);
    for (uint32_t seq = first; seq <= latest; seq++) {
        event_item_t *item = &ring[seq % EVENTS];
        if (seq > after && item->json) {
            cJSON *parsed = cJSON_Parse(item->json);
            if (parsed) cJSON_AddItemToArray(list, parsed);
        }
    }
    xSemaphoreGive(ring_mutex);
    return json_response(req, obj);
}

static esp_err_t ota_handler(httpd_req_t *req)
{
    if (!require_auth(req)) return ESP_FAIL;
    if (pending_verify) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "confirm current trial image first");
    char sha[65], target[16];
    uint8_t expected_digest[32], digest[32];
    if (httpd_req_get_hdr_value_str(req, "X-SHA256", sha, sizeof(sha)) != ESP_OK ||
        hm_unhex(sha, expected_digest, sizeof(expected_digest)) != 32 ||
        httpd_req_get_hdr_value_str(req, "X-Target", target, sizeof(target)) != ESP_OK || strcmp(target, "esp32c6") != 0)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "target and SHA-256 required");
    const esp_partition_t *next = esp_ota_get_next_update_partition(NULL);
    if (!next || req->content_len < 288 || req->content_len > next->size)
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "app image size outside OTA partition");
    esp_ota_handle_t handle = 0;
    esp_err_t result = esp_ota_begin(next, req->content_len, &handle);
    if (result != ESP_OK) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "OTA begin failed");
    mbedtls_sha256_context hash;
    mbedtls_sha256_init(&hash);
    mbedtls_sha256_starts(&hash, 0);
    uint8_t *buffer = malloc(4096);
    if (!buffer) result = ESP_ERR_NO_MEM;
    int remaining = req->content_len;
    while (result == ESP_OK && remaining > 0) {
        int count = httpd_req_recv(req, (char *)buffer, remaining > 4096 ? 4096 : remaining);
        if (count <= 0) { result = ESP_FAIL; break; }
        if (mbedtls_sha256_update(&hash, buffer, count) != 0) { result = ESP_FAIL; break; }
        result = esp_ota_write(handle, buffer, count);
        remaining -= count;
    }
    free(buffer);
    if (result == ESP_OK && mbedtls_sha256_finish(&hash, digest) != 0) result = ESP_FAIL;
    mbedtls_sha256_free(&hash);
    if (result == ESP_OK && memcmp(digest, expected_digest, 32) != 0) result = ESP_ERR_INVALID_CRC;
    if (result != ESP_OK) {
        esp_ota_abort(handle);
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "upload incomplete or checksum invalid; current image retained");
    }
    result = esp_ota_end(handle); // Validates the image and target chip before selection.
    esp_app_desc_t desc;
    if (result == ESP_OK) result = esp_ota_get_partition_description(next, &desc);
    if (result == ESP_OK && strcmp(desc.project_name, "hue_mesh_lab") != 0) result = ESP_ERR_INVALID_ARG;
    if (result == ESP_OK) result = esp_ota_set_boot_partition(next);
    if (result != ESP_OK) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "not a valid matching app; current image retained");
    char elf[65];
    hm_hex(desc.app_elf_sha256, 32, elf);
    cJSON *obj = cJSON_CreateObject();
    cJSON_AddBoolToObject(obj, "ok", true);
    cJSON_AddBoolToObject(obj, "restarting", true);
    cJSON_AddStringToObject(obj, "elf_sha256", elf);
    cJSON_AddStringToObject(obj, "partition", next->label);
    result = json_response(req, obj);
    esp_timer_start_once(restart_timer, 750000);
    return result;
}

static esp_err_t confirm_handler(httpd_req_t *req)
{
    if (!require_auth(req)) return ESP_FAIL;
    cJSON *obj = read_json(req);
    const cJSON *expected_hash = cJSON_GetObjectItemCaseSensitive(obj, "elf_sha256");
    char elf[65];
    hm_hex(esp_app_get_description()->app_elf_sha256, 32, elf);
    bool match = cJSON_IsString(expected_hash) && strcmp(expected_hash->valuestring, elf) == 0;
    cJSON_Delete(obj);
    if (!match) return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "running image identity mismatch");
    esp_err_t result = pending_verify ? esp_ota_mark_app_valid_cancel_rollback() : ESP_OK;
    if (result != ESP_OK) return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "confirmation failed");
    pending_verify = false;
    esp_timer_stop(rollback_timer);
    obj = cJSON_CreateObject();
    cJSON_AddBoolToObject(obj, "ok", true);
    cJSON_AddStringToObject(obj, "elf_sha256", elf);
    return json_response(req, obj);
}

static esp_err_t start_server(void)
{
    if (server) return ESP_OK;
    httpd_ssl_config_t config = HTTPD_SSL_CONFIG_DEFAULT();
    config.httpd.stack_size = 12288;
    config.httpd.max_open_sockets = 3;
    config.httpd.lru_purge_enable = true;
    config.httpd.keep_alive_enable = true;
    config.httpd.keep_alive_idle = 10;
    config.httpd.keep_alive_interval = 5;
    config.httpd.keep_alive_count = 3;
    config.httpd.max_uri_handlers = 5;
    config.httpd.recv_wait_timeout = 15;
    config.httpd.send_wait_timeout = 15;
    config.servercert = (const uint8_t *)cert;
    config.servercert_len = strlen(cert) + 1;
    config.prvtkey_pem = (const uint8_t *)key;
    config.prvtkey_len = strlen(key) + 1;
    esp_err_t result = httpd_ssl_start(&server, &config);
    if (result != ESP_OK) return result;
    httpd_uri_t endpoints[] = {
        {.uri = "/api/status", .method = HTTP_GET, .handler = status_handler},
        {.uri = "/api/command", .method = HTTP_POST, .handler = command_handler},
        {.uri = "/api/events", .method = HTTP_GET, .handler = events_handler},
        {.uri = "/api/ota", .method = HTTP_POST, .handler = ota_handler},
        {.uri = "/api/ota/confirm", .method = HTTP_POST, .handler = confirm_handler},
    };
    for (size_t i = 0; i < sizeof(endpoints) / sizeof(endpoints[0]); i++) {
        result = httpd_register_uri_handler(server, &endpoints[i]);
        if (result != ESP_OK) { httpd_ssl_stop(server); server = NULL; return result; }
    }
    return ESP_OK;
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg; (void)data;
    if (base == WIFI_EVENT && (id == WIFI_EVENT_STA_START || id == WIFI_EVENT_STA_DISCONNECTED)) {
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        esp_err_t result = start_server();
        cJSON *event = cJSON_CreateObject();
        cJSON_AddStringToObject(event, "event", "wifi_ready");
        cJSON_AddNumberToObject(event, "server_status", result);
        hm_net_info(event);
        char *json = cJSON_PrintUnformatted(event);
        if (json) { hm_net_emit(json, -1, true); free(json); }
        cJSON_Delete(event);
    }
}

esp_err_t hm_net_init(void)
{
    ring_mutex = xSemaphoreCreateMutex();
    request_mutex = xSemaphoreCreateMutex();
    replies = xQueueCreate(4, sizeof(reply_item_t));
    if (!ring_mutex || !request_mutex || !replies) return ESP_ERR_NO_MEM;
    ESP_ERROR_CHECK(nvs_open("hue_mesh_net", NVS_READWRITE, &storage));
    ESP_ERROR_CHECK(certificate());
    size_t len = sizeof(api_token);
    configured = nvs_get_str(storage, "token", api_token, &len) == ESP_OK && token_valid(api_token);
    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_read_mac(mac, ESP_MAC_WIFI_STA));
    snprintf(hostname, sizeof(hostname), "hue-mesh-%02x%02x%02x", mac[3], mac[4], mac[5]);
    esp_timer_create_args_t timer = {.callback = restart, .name = "ota_rollback"};
    ESP_ERROR_CHECK(esp_timer_create(&timer, &rollback_timer));
    timer.name = "ota_restart";
    ESP_ERROR_CHECK(esp_timer_create(&timer, &restart_timer));
    esp_ota_img_states_t state;
    pending_verify = esp_ota_get_state_partition(esp_ota_get_running_partition(), &state) == ESP_OK && state == ESP_OTA_IMG_PENDING_VERIFY;
    if (pending_verify) ESP_ERROR_CHECK(esp_timer_start_once(rollback_timer, VERIFY_SECONDS * 1000000ULL));
    return ESP_OK;
}

esp_err_t hm_net_start(void)
{
    if (!configured || wifi_started) return ESP_OK;
    char ssid[33], password[65];
    size_t ssid_len = sizeof(ssid), password_len = sizeof(password);
    if (nvs_get_str(storage, "ssid", ssid, &ssid_len) != ESP_OK || nvs_get_str(storage, "password", password, &password_len) != ESP_OK) return ESP_FAIL;
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    station = esp_netif_create_default_wifi_sta();
    if (!station) return ESP_ERR_NO_MEM;
    ESP_ERROR_CHECK(esp_netif_set_hostname(station, hostname));
    wifi_init_config_t init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    wifi_config_t config = {0};
    memcpy(config.sta.ssid, ssid, strlen(ssid));
    memcpy(config.sta.password, password, strlen(password));
    config.sta.sae_pwe_h2e = WPA3_SAE_PWE_BOTH;
    config.sta.pmf_cfg.capable = true;
    memset(password, 0, sizeof(password));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &config));
    ESP_ERROR_CHECK(esp_wifi_start());
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_MIN_MODEM));
    ESP_ERROR_CHECK(esp_coex_wifi_i154_enable());
    wifi_started = true;
    return ESP_OK;
}

esp_err_t hm_net_configure(const cJSON *request)
{
    const cJSON *ssid = cJSON_GetObjectItemCaseSensitive(request, "ssid");
    const cJSON *password = cJSON_GetObjectItemCaseSensitive(request, "password");
    const cJSON *token = cJSON_GetObjectItemCaseSensitive(request, "token");
    if (!cJSON_IsString(ssid) || !strlen(ssid->valuestring) || strlen(ssid->valuestring) > 32 ||
        !cJSON_IsString(password) || strlen(password->valuestring) > 63 ||
        !cJSON_IsString(token) || !token_valid(token->valuestring)) return ESP_ERR_INVALID_ARG;
    if (nvs_set_str(storage, "ssid", ssid->valuestring) != ESP_OK ||
        nvs_set_str(storage, "password", password->valuestring) != ESP_OK ||
        nvs_set_str(storage, "token", token->valuestring) != ESP_OK || nvs_commit(storage) != ESP_OK) return ESP_FAIL;
    memcpy(api_token, token->valuestring, 65);
    configured = true;
    if (wifi_started) {
        esp_timer_start_once(restart_timer, 750000);
        return ESP_OK;
    }
    return hm_net_start();
}

#else
esp_err_t hm_net_init(void) { return ESP_OK; }
esp_err_t hm_net_start(void) { return ESP_OK; }
esp_err_t hm_net_configure(const cJSON *request) { (void)request; return ESP_ERR_NOT_SUPPORTED; }
void hm_net_emit(const char *json, int id, bool is_event) { (void)json; (void)id; (void)is_event; }
void hm_net_info(cJSON *object)
{
    cJSON *net = cJSON_AddObjectToObject(object, "network");
    cJSON_AddBoolToObject(net, "supported", false);
    cJSON_AddBoolToObject(net, "ota", false);
    cJSON_AddStringToObject(net, "reason", "ESP32-H2 has no Wi-Fi; use C6 for remote updates");
}
#endif
