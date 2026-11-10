// SPDX-License-Identifier: MIT
#include <assert.h>
#include <stdio.h>
#include "../hue-direct/firmware-source/main/player.c"
#include "../hue-direct/firmware-source/main/direct_program.h"
static uint8_t network[8];static bool journal;static unsigned fault,commits,erases;
int64_t esp_timer_get_time(void) {return 1000000;}
void esp_zb_get_extended_pan_id(uint8_t *out) {memcpy(out,network,8);}
esp_err_t nvs_set_str(nvs_handle_t h,const char *k,const char *v) {(void)h;(void)v;assert(!strcmp(k,"journal"));if(fault==1)return ESP_ERR_NO_MEM;journal=true;return ESP_OK;}
esp_err_t nvs_set_u8(nvs_handle_t h,const char *k,uint8_t v) {(void)h;(void)v;return (fault==2 || fault==4) && !strcmp(k,"take")?ESP_ERR_NO_MEM:ESP_OK;}
esp_err_t nvs_commit(nvs_handle_t h) {(void)h;commits++;return fault==3 && commits==1?ESP_ERR_NO_MEM:ESP_OK;}
esp_err_t nvs_erase_key(nvs_handle_t h,const char *k) {(void)h;assert(!strcmp(k,"journal"));erases++;if(fault==4)return ESP_ERR_NO_MEM;journal=false;return ESP_OK;}
static cJSON *request(void) {
 hd_scene_t scene;hd_defaults(&scene);hd_snapshot_t before={.level=25,.mode=2,.capacity=10,.regions=7,.x=30121,.y=26905,.temperature=370};
 for(unsigned i=0;i<7;i++) {before.starts[i]=i;before.lengths[i]=i==6?21:1;before.aliases[i]=100+i;}
 return hd_prepare_program(&scene,&before,"0017880102030405","0102030405060708",123,11,true);
}
int main(void) {
 assert(hm_eui64("0102030405060708",network));
 for(fault=1;fault<=3;fault++) {
  durable=playing=restoring=configuring=false;commits=erases=0;journal=false;
  cJSON *q=request(),*r=hm_player_command(q,true);assert(!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(r,"ok")) && !journal && !durable && erases==1);cJSON_Delete(q);cJSON_Delete(r);
  puts(fault==1?"PASS rejected journal write leaves no recovery record":fault==2?"PASS metadata failure erases an unstarted journal":"PASS commit failure rolls back the unstarted journal");
 }
 // Fail a metadata write AND its cleanup. Ownership must remain durable so a
 // caller cannot start another player or OTA while recovery is unresolved.
 fault=4;durable=playing=restoring=configuring=false;commits=erases=0;journal=false;
 cJSON *q=request(),*r=hm_player_command(q,true);assert(!cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(r,"ok")) && journal && durable);cJSON_Delete(r);puts("PASS failed rollback keeps durable recovery ownership");
 fault=0;durable=false;r=hm_player_command(q,true);assert(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(r,"ok")) && journal && durable);cJSON_Delete(r);cJSON_Delete(q);puts("PASS valid production recovery program is accepted and owned");
 return 0;
}
