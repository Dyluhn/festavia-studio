// SPDX-License-Identifier: MIT
#include <assert.h>
#include "../hue-direct/firmware-source/main/direct_storage.c"
static esp_flash_t chip={0x400000};esp_flash_t *esp_flash_default_chip=&chip;
static esp_partition_t parts[8];static unsigned part_count,registrations,initializations,reads,copies,erases;
static bool blank,old_present,reserved,migrated,fresh_committed,fail_meta,fail_copy,fail_commit,fail_init;
struct iterator {unsigned i;};
static void part(unsigned address,unsigned size,const char *label) {esp_partition_t *p=&parts[part_count++];*p=(esp_partition_t){.address=address,.size=size,.type=1,.subtype=2,.flash_chip=&chip};strcpy(p->label,label);}
static void reset(void) {
 part_count=registrations=initializations=reads=copies=erases=0;blank=old_present=true;reserved=migrated=fresh_committed=fail_meta=fail_copy=fail_commit=fail_init=false;
 part(0x9000,0x6000,"nvs");part(0xf000,0x2000,"otadata");part(0x11000,0x1000,"phy_init");part(0x20000,0x1e0000,"ota_0");part(0x200000,0x1e0000,"ota_1");
}
const esp_partition_t *esp_partition_find_first(unsigned type,unsigned sub,const char *label) {(void)type;(void)sub;for(unsigned i=0;i<part_count;i++)if(!strcmp(parts[i].label,label))return &parts[i];return NULL;}
esp_partition_iterator_t esp_partition_find(unsigned t,unsigned s,const char *l) {(void)t;(void)s;(void)l;struct iterator *it=malloc(sizeof(*it));it->i=0;return it;}
const esp_partition_t *esp_partition_get(esp_partition_iterator_t it) {return &parts[it->i];}
esp_partition_iterator_t esp_partition_next(esp_partition_iterator_t it) {if(++it->i<part_count)return it;free(it);return NULL;}
void esp_partition_iterator_release(esp_partition_iterator_t it) {free(it);}
esp_err_t esp_partition_register_external(esp_flash_t *c,size_t a,size_t n,const char *l,unsigned t,unsigned s,const esp_partition_t **out) {(void)t;(void)s;assert(c==&chip && a==0x12000 && n==0xe000 && reserved);registrations++;part(a,n,l);if(out)*out=&parts[part_count-1];return ESP_OK;}
esp_err_t esp_flash_read(esp_flash_t *c,void *data,uint32_t offset,uint32_t size) {assert(c==&chip && offset>=0x12000 && offset+size<=0x20000);reads++;memset(data,blank?0xff:0x42,size);return ESP_OK;}
esp_err_t nvs_open(const char *name,int mode,nvs_handle_t *h) {if(!strcmp(name,"hd_store_meta")) {*h=3;return ESP_OK;}assert(!strcmp(name,"hue_direct"));if(!old_present && mode==NVS_READONLY)return ESP_ERR_NVS_NOT_FOUND;*h=1;return ESP_OK;}
esp_err_t nvs_open_from_partition(const char *p,const char *ns,int mode,nvs_handle_t *h) {(void)mode;assert(!strcmp(p,"hd_store") && !strcmp(ns,"hue_direct"));*h=2;return ESP_OK;}
esp_err_t nvs_get_u8(nvs_handle_t h,const char *k,uint8_t *v) {if(h==3 && !strcmp(k,"reserved")) {*v=reserved;return ESP_OK;}if(h==2 && !strcmp(k,"_migrated")) {*v=migrated;return ESP_OK;}if(h==1) {*v=1;return ESP_OK;}return ESP_ERR_NVS_NOT_FOUND;}
esp_err_t nvs_set_u8(nvs_handle_t h,const char *k,uint8_t v) {if(h==3) {assert(!strcmp(k,"reserved"));reserved=v;}if(h==2 && !strcmp(k,"_migrated"))migrated=v;return ESP_OK;}
esp_err_t nvs_commit(nvs_handle_t h) {if((h==3 && fail_meta) || (h==2 && fail_commit))return ESP_ERR_NO_MEM;if(h==2)fresh_committed=true;return ESP_OK;}
void nvs_close(nvs_handle_t h) {(void)h;}
esp_err_t nvs_get_blob(nvs_handle_t h,const char *k,void *data,size_t *n) {assert(h==1);size_t size=!strcmp(k,"target")?8:436;if(data) {assert(*n==size);memset(data,0,size);}*n=size;return ESP_OK;}
esp_err_t nvs_get_str(nvs_handle_t h,const char *k,char *data,size_t *n) {assert(h==1 && !strcmp(k,"bridge"));if(data) {assert(*n==3);memcpy(data,"{}",3);}*n=3;return ESP_OK;}
esp_err_t nvs_set_blob(nvs_handle_t h,const char *k,const void *data,size_t n) {(void)k;(void)data;(void)n;assert(h==2);copies++;return fail_copy?ESP_ERR_NO_MEM:ESP_OK;}
esp_err_t nvs_set_str(nvs_handle_t h,const char *k,const char *v) {(void)k;(void)v;assert(h==2);copies++;return ESP_OK;}
esp_err_t nvs_erase_all(nvs_handle_t h) {assert(h==1 && migrated && fresh_committed);erases++;old_present=false;return ESP_OK;}
esp_err_t nvs_flash_init_partition(const char *name) {assert(!strcmp(name,"hd_store"));initializations++;return fail_init?ESP_ERR_NO_MEM:ESP_OK;}
int main(void) {
 reset();assert(hd_storage_init()==ESP_OK && reserved && registrations==1 && initializations==1 && copies==19 && erases==1);puts("PASS legacy migration commits before old namespace removal");
 reset();blank=false;assert(hd_storage_init()==ESP_ERR_INVALID_STATE && !registrations && !initializations && !erases);puts("PASS unknown nonblank gap is refused");
 reset();parts[3].address=0x30000;assert(hd_storage_init()==ESP_ERR_INVALID_STATE && !reads && !reserved);puts("PASS unexpected OTA layout is refused");
 reset();part(0x12000,0x1000,"foreign");assert(hd_storage_init()==ESP_ERR_INVALID_STATE && !reads && !reserved);puts("PASS overlapping partition is refused");
 reset();part(0x12000,0xd000,"hd_store");assert(hd_storage_init()==ESP_ERR_INVALID_STATE && !initializations);puts("PASS wrong named store geometry is refused");
 reset();part(0x12000,0xe000,"hd_store");assert(hd_storage_init()==ESP_OK && !registrations && !reads && initializations==1);puts("PASS declared factory store needs no gap registration");
 reset();fail_meta=true;assert(hd_storage_init()!=ESP_OK && !initializations && !erases);puts("PASS reservation failure performs no store write");
 reset();fail_copy=true;assert(hd_storage_init()!=ESP_OK && !erases && old_present);puts("PASS copy failure preserves original settings");
 reset();fail_commit=true;assert(hd_storage_init()!=ESP_OK && !erases && old_present);puts("PASS new-store commit failure preserves original settings");
 reset();reserved=true;blank=old_present=false;assert(hd_storage_init()==ESP_OK && !reads && registrations==1 && !erases);puts("PASS reserved store resumes after interrupted initialization");
 reset();fail_init=true;assert(hd_storage_init()!=ESP_OK && !erases && old_present);puts("PASS NVS initialization error never auto-erases settings");
 reset();reserved=migrated=fresh_committed=true;blank=false;assert(hd_storage_init()==ESP_OK && !copies && erases==1);puts("PASS committed migration resumes cleanup without copying stale settings");
 reset();old_present=false;part(0x12000,0xe000,"hd_store");assert(hd_storage_init()==ESP_OK && migrated && fresh_committed && !erases);puts("PASS factory initialization marks the store against stale future migration");
 return 0;
}
