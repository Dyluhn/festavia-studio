// SPDX-License-Identifier: MIT
// Pinned outgoing Hue API connection. No Home Assistant or external daemon.
#include "direct.h"
#include "direct_storage.h"
#include "direct_json.h"
#include "wire.h"
#include "nvs.h"
#include "esp_http_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/ssl.h"
#include "mbedtls/x509_crt.h"
#include "mbedtls/sha256.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

typedef struct { char host[64], key[128], resource[64]; uint8_t pin[32]; } bridge_config_t;
static bridge_config_t pending_config, active_config;
static bool configured;
static unsigned generation;
static const mbedtls_x509_crt dummy_ca;
static esp_err_t last_error;static int last_http;static unsigned requests;static const char *phase="unconfigured";
static void diagnostic(const char *p,esp_err_t error,int status) {esp_zb_lock_acquire(portMAX_DELAY);phase=p;last_error=error;last_http=status;requests++;esp_zb_lock_release();}
void hd_bridge_details(cJSON *r) {cJSON_AddStringToObject(r,"bridge_phase",phase);cJSON_AddStringToObject(r,"bridge_error",esp_err_to_name(last_error));cJSON_AddNumberToObject(r,"bridge_http",last_http);cJSON_AddNumberToObject(r,"bridge_requests",requests);}
static int verify(void *context,mbedtls_x509_crt *certificate,int depth,uint32_t *flags) {
    (void)context;
    if(depth==0) {
        uint8_t hash[32];mbedtls_sha256(certificate->raw.p,certificate->raw.len,hash,0);
        unsigned difference=0;for(unsigned i=0;i<32;i++)difference|=hash[i]^active_config.pin[i];
        if(difference) {*flags=MBEDTLS_X509_BADCERT_NOT_TRUSTED;return MBEDTLS_ERR_X509_CERT_VERIFY_FAILED;}
    }
    // The enrolled exact leaf pin is the trust anchor, also without wall time.
    // No CA/hostname fallback and no credentials on a mismatched TLS connection.
    *flags=0;return 0;
}
static esp_err_t attach(void *configuration) {
    mbedtls_ssl_config *config=configuration;
    mbedtls_ssl_conf_ca_chain(config,(mbedtls_x509_crt *)&dummy_ca,NULL);
    mbedtls_ssl_conf_authmode(config,MBEDTLS_SSL_VERIFY_REQUIRED);
    mbedtls_ssl_conf_verify(config,verify,NULL);return ESP_OK;
}
typedef struct {char *data;size_t size;bool failed;} response_t;
static esp_err_t event(esp_http_client_event_t *e) {
    response_t *r=e->user_data;
    if(e->event_id==HTTP_EVENT_ON_DATA && e->data_len>0) {
        if(r->size+(unsigned)e->data_len>32768) {r->failed=true;return ESP_ERR_INVALID_SIZE;}
        char *next=realloc(r->data,r->size+e->data_len+1);if(!next) {r->failed=true;return ESP_ERR_NO_MEM;}
        r->data=next;memcpy(r->data+r->size,e->data,e->data_len);r->size+=e->data_len;r->data[r->size]=0;
    }
    return ESP_OK;
}
static const char *str(const cJSON *o,const char *k) {const cJSON *v=cJSON_GetObjectItemCaseSensitive(o,k);return cJSON_IsString(v)?v->valuestring:NULL;}
bool hd_bridge_configure(const cJSON *config) {
    const char *h=str(config,"host"),*k=str(config,"key"),*fingerprint=str(config,"pin"),*id=str(config,"light");uint8_t temp[32];
    if(!h || !k || !id || strlen(h)>=sizeof(pending_config.host) || strlen(k)<16 || strlen(k)>=sizeof(pending_config.key) || strlen(id)!=36 || hm_unhex(fingerprint,temp,32)!=32)return false;
    // Enrollment resolves a private address first; the device accepts literals.
    unsigned a,b,c,d;char extra;
    if(sscanf(h,"%u.%u.%u.%u%c",&a,&b,&c,&d,&extra)!=4 || a>255 || b>255 || c>255 || d>255 ||
       !(a==10 || (a==172 && b>=16 && b<=31) || (a==192 && b==168)))return false;
    for(unsigned i=0;i<36;i++)if(!((id[i]>='0' && id[i]<='9') || (id[i]>='a' && id[i]<='f') || id[i]=='-'))return false;
    char *body=cJSON_PrintUnformatted(config);if(!body)return false;
    nvs_handle_t storage;esp_err_t e=hd_storage_open(NVS_READWRITE,&storage);
    if(e==ESP_OK) {e=nvs_set_str(storage,"bridge",body);if(e==ESP_OK)e=nvs_commit(storage);nvs_close(storage);}
    free(body);if(e!=ESP_OK)return false;
    strcpy(pending_config.host,h);strcpy(pending_config.key,k);strcpy(pending_config.resource,id);memcpy(pending_config.pin,temp,32);configured=true;generation++;return true;
}
static bool fetch(esp_http_client_handle_t client,response_t *response,const char *path) {
    char url[192];snprintf(url,sizeof(url),"https://%s%s",active_config.host,path);
    free(response->data);response->data=NULL;response->size=0;response->failed=false;
    esp_err_t e=esp_http_client_set_url(client,url);if(e!=ESP_OK) {diagnostic("url",e,0);return false;}
    esp_http_client_set_header(client,"hue-application-key",active_config.key);
    esp_http_client_set_method(client,HTTP_METHOD_GET);esp_http_client_set_post_field(client,NULL,0);
    e=esp_http_client_perform(client);int status=esp_http_client_get_status_code(client);diagnostic("request",e,status);
    return e==ESP_OK && status==200 && response->data && !response->failed;
}
static bool replay(esp_http_client_handle_t client,response_t *response,const cJSON *patch) {
    char url[192];snprintf(url,sizeof(url),"https://%s/clip/v2/resource/light/%s",active_config.host,active_config.resource);
    char *body=cJSON_PrintUnformatted(patch);if(!body)return false;
    free(response->data);response->data=NULL;response->size=0;response->failed=false;
    esp_err_t e=esp_http_client_set_url(client,url);
    if(e==ESP_OK)e=esp_http_client_set_method(client,HTTP_METHOD_PUT);
    if(e==ESP_OK)e=esp_http_client_set_header(client,"Content-Type","application/json");
    if(e==ESP_OK)e=esp_http_client_set_post_field(client,body,strlen(body));
    if(e==ESP_OK)e=esp_http_client_perform(client);
    int status=esp_http_client_get_status_code(client);diagnostic("handoff",e,status);
    esp_http_client_set_post_field(client,NULL,0);free(body);
    cJSON *result=response->data?cJSON_Parse(response->data):NULL;
    bool ok=e==ESP_OK && (status==200 || status==207) && !response->failed && result;
    const cJSON *errors=cJSON_GetObjectItemCaseSensitive(result,"errors");
    if(!cJSON_IsArray(errors))ok=false;
    for(const cJSON *v=errors?errors->child:NULL;v;v=v->next) {const char *code=str(v,"error_code");if(!code || strcmp(code,"attribute_may_have_no_effect"))ok=false;}
    cJSON_Delete(result);return ok;
}
static void task(void *argument) {
    (void)argument;esp_http_client_handle_t client=NULL;response_t response={0};unsigned current=0;
    for(;;) {
        esp_zb_lock_acquire(portMAX_DELAY);
        bool run=configured && (hd_enabled() || hd_owns_player());unsigned next=generation;
        bridge_config_t next_config=pending_config;
        esp_zb_lock_release();
        if(run) {
            if(current!=next) {
                if(client) {esp_http_client_cleanup(client);client=NULL;}
                active_config=next_config;current=next;
            }
            if(!client) {
                char url[128];snprintf(url,sizeof(url),"https://%s",active_config.host);
                esp_http_client_config_t config={.url=url,.timeout_ms=3000,.crt_bundle_attach=attach,.skip_cert_common_name_check=true,
                    .event_handler=event,.user_data=&response,.keep_alive_enable=true,.buffer_size=1024,.buffer_size_tx=512};
                client=esp_http_client_init(&config);
            }
            cJSON *light=NULL;bool active=false,inventory_ok=false;
            if(client && fetch(client,&response,"/clip/v2/resource/entertainment_configuration")) {
                inventory_ok=hd_entertainment(response.data,response.size,&active);
                if(!inventory_ok)diagnostic("entertainment_json",ESP_ERR_INVALID_RESPONSE,200);
            }
            if(inventory_ok) {
                char path[96];snprintf(path,sizeof(path),"/clip/v2/resource/light/%s",active_config.resource);
                if(fetch(client,&response,path))light=cJSON_Parse(response.data);
            }
            bool ok=inventory_ok && light && !cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(light,"errors")) && cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(light,"data"))==1;
            esp_zb_lock_acquire(portMAX_DELAY);
            hd_bridge_observation(ok && current==generation,active,ok?cJSON_GetArrayItem(cJSON_GetObjectItemCaseSensitive(light,"data"),0):NULL);
            cJSON *patch=ok && current==generation?hd_bridge_replay():NULL;
            esp_zb_lock_release();
            cJSON_Delete(light);
            if(patch) {bool sent=replay(client,&response,patch);cJSON_Delete(patch);esp_zb_lock_acquire(portMAX_DELAY);hd_bridge_replayed(sent);esp_zb_lock_release();}
            if(!ok && client) {esp_http_client_cleanup(client);client=NULL;}
        } else if(client) {esp_http_client_cleanup(client);client=NULL;}
        free(response.data);response.data=NULL;response.size=0;
        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}
void hd_bridge_start(void) {
    nvs_handle_t storage;if(hd_storage_open(NVS_READONLY,&storage)==ESP_OK) {
        size_t size=0;
        if(nvs_get_str(storage,"bridge",NULL,&size)==ESP_OK && size<2048) {
            char *body=malloc(size);if(body && nvs_get_str(storage,"bridge",body,&size)==ESP_OK) {
                cJSON *config=cJSON_Parse(body);hd_bridge_configure(config);cJSON_Delete(config);
            }
            free(body);
        }
        nvs_close(storage);
    }
    configASSERT(xTaskCreate(task,"hue_guard",8192,NULL,3,NULL)==pdPASS);
}
