// SPDX-License-Identifier: MIT
#include "direct_storage.h"
#include "esp_partition.h"
#include "esp_flash.h"
#include "nvs_flash.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define STORE_START 0x12000
#define STORE_SIZE 0xe000
#define STORE_END (STORE_START+STORE_SIZE)
static esp_err_t existing_layout(void) {
    const struct {const char *name;unsigned offset,size;} required[]={
        {"nvs",0x9000,0x6000},{"otadata",0xf000,0x2000},{"phy_init",0x11000,0x1000},
        {"ota_0",0x20000,0x1e0000},{"ota_1",0x200000,0x1e0000}};
    for(unsigned i=0;i<sizeof(required)/sizeof(required[0]);i++) {
        const esp_partition_t *p=esp_partition_find_first(ESP_PARTITION_TYPE_ANY,ESP_PARTITION_SUBTYPE_ANY,required[i].name);
        if(!p || p->address!=required[i].offset || p->size!=required[i].size || p->flash_chip!=esp_flash_default_chip || p->encrypted)return ESP_ERR_INVALID_STATE;
    }
    esp_partition_iterator_t it=esp_partition_find(ESP_PARTITION_TYPE_ANY,ESP_PARTITION_SUBTYPE_ANY,NULL);
    while(it) {
        const esp_partition_t *p=esp_partition_get(it);
        if(p->flash_chip==esp_flash_default_chip && p->address<STORE_END && p->address+p->size>STORE_START) {esp_partition_iterator_release(it);return ESP_ERR_INVALID_STATE;}
        it=esp_partition_next(it);
    }
    return ESP_OK;
}
static esp_err_t reserve_legacy_gap(void) {
    esp_err_t e=existing_layout();if(e!=ESP_OK)return e;
    nvs_handle_t meta;e=nvs_open("hd_store_meta",NVS_READWRITE,&meta);if(e!=ESP_OK)return e;
    uint8_t reserved=0;nvs_get_u8(meta,"reserved",&reserved);
    if(!reserved) {
        uint8_t data[256];
        for(unsigned offset=STORE_START;offset<STORE_END;offset+=sizeof(data)) {
            e=esp_flash_read(esp_flash_default_chip,data,offset,sizeof(data));if(e!=ESP_OK)break;
            for(unsigned i=0;i<sizeof(data);i++)if(data[i]!=0xff) {e=ESP_ERR_INVALID_STATE;break;}
            if(e!=ESP_OK)break;
        }
        // Commit ownership BEFORE the first gap write. A power cut during NVS
        // initialization can then safely resume; unknown nonblank data is refused.
        if(e==ESP_OK)e=nvs_set_u8(meta,"reserved",1);
        if(e==ESP_OK)e=nvs_commit(meta);
    }
    nvs_close(meta);if(e!=ESP_OK)return e;
    return esp_partition_register_external(esp_flash_default_chip,STORE_START,STORE_SIZE,"hd_store",ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,NULL);
}
static esp_err_t copy_blob(nvs_handle_t old,nvs_handle_t fresh,const char *key,bool string) {
    size_t n=0;esp_err_t e=string?nvs_get_str(old,key,NULL,&n):nvs_get_blob(old,key,NULL,&n);
    if(e==ESP_ERR_NVS_NOT_FOUND)return ESP_OK;
    if(e!=ESP_OK || n>2048)return e==ESP_OK?ESP_ERR_INVALID_SIZE:e;
    void *data=malloc(n?n:1);if(!data)return ESP_ERR_NO_MEM;
    e=string?nvs_get_str(old,key,data,&n):nvs_get_blob(old,key,data,&n);
    if(e==ESP_OK)e=string?nvs_set_str(fresh,key,data):nvs_set_blob(fresh,key,data,n);
    free(data);return e;
}
esp_err_t hd_storage_open(int mode,nvs_handle_t *handle) {return nvs_open_from_partition("hd_store","hue_direct",mode,handle);}
esp_err_t hd_storage_init(void) {
    const esp_partition_t *p=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"hd_store");
    esp_err_t e;
    if(p) {if(p->address!=STORE_START || p->size!=STORE_SIZE || p->flash_chip!=esp_flash_default_chip || p->encrypted)return ESP_ERR_INVALID_STATE;}
    else {e=reserve_legacy_gap();if(e!=ESP_OK)return e;}
    e=nvs_flash_init_partition("hd_store");if(e!=ESP_OK)return e; // Never auto-erase settings on errors.
    nvs_handle_t fresh,old;e=hd_storage_open(NVS_READWRITE,&fresh);if(e!=ESP_OK)return e;
    uint8_t migrated=0;nvs_get_u8(fresh,"_migrated",&migrated);
    e=nvs_open("hue_direct",NVS_READONLY,&old);
    if(e==ESP_ERR_NVS_NOT_FOUND) {e=nvs_set_u8(fresh,"_migrated",1);if(e==ESP_OK)e=nvs_commit(fresh);nvs_close(fresh);return e;}
    if(e!=ESP_OK) {nvs_close(fresh);return e;}
    if(!migrated) {
        const char *flags[]={"enabled","count","takeover","limit"};
        for(unsigned i=0;i<sizeof(flags)/sizeof(flags[0]) && e==ESP_OK;i++) {
            uint8_t value;esp_err_t found=nvs_get_u8(old,flags[i],&value);
            if(found==ESP_OK)e=nvs_set_u8(fresh,flags[i],value);else if(found!=ESP_ERR_NVS_NOT_FOUND)e=found;
        }
        if(e==ESP_OK)e=copy_blob(old,fresh,"target",false);
        if(e==ESP_OK)e=copy_blob(old,fresh,"scene",false);
        if(e==ESP_OK)e=copy_blob(old,fresh,"bridge",true);
        for(unsigned i=0;i<16 && e==ESP_OK;i++) {char key[24];snprintf(key,sizeof(key),"preset%u",i);e=copy_blob(old,fresh,key,false);}
        if(e==ESP_OK)e=nvs_set_u8(fresh,"_migrated",1);
        if(e==ESP_OK)e=nvs_commit(fresh);
    }
    nvs_close(old);nvs_close(fresh);if(e!=ESP_OK)return e;
    // Only this edition's old namespace is removed, after the new copy commits.
    // Wi-Fi, TLS identity, Zigbee selection and the player journal are untouched.
    e=nvs_open("hue_direct",NVS_READWRITE,&old);if(e!=ESP_OK)return e;
    e=nvs_erase_all(old);if(e==ESP_OK)e=nvs_commit(old);nvs_close(old);return e;
}

void hd_storage_details(cJSON *r) {
    nvs_stats_t stats;
    if(nvs_get_stats("nvs",&stats)==ESP_OK)cJSON_AddNumberToObject(r,"recovery_nvs_free_entries",stats.free_entries);
    if(nvs_get_stats("hd_store",&stats)==ESP_OK)cJSON_AddNumberToObject(r,"settings_nvs_free_entries",stats.free_entries);
}
