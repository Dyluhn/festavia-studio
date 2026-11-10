// SPDX-License-Identifier: MIT
// Standalone Hue control surface. Runs under the Zigbee lock except init.
#include "direct.h"
#include "direct_storage.h"
#include "direct_program.h"
#include "player.h"
#include "wire.h"
#include "nvs.h"
#include "esp_timer.h"
#include "esp_zigbee_attribute.h"
#include "esp_zigbee_cluster.h"
#include "ha/esp_zigbee_ha_standard.h"
#include "zdo/esp_zigbee_zdo_command.h"
#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

#define FIRST_EP 11
#define LAST_EP 19
#define CLIENT_EP 20
#define MFG 0x100b
static nvs_handle_t storage;
static hd_scene_t scene, active_scene, presets[HD_PRESETS];
static bool saved[HD_PRESETS], enabled, configured, master, owns, dirty, explicit_apply, updating;
static uint8_t layer, position=1, shape_parameter, preset=1, positions=1, allow_hue_takeover=1;
static uint8_t target_ieee[8], target_endpoint=11, query_tsn, query_command;
static uint16_t target_address, query_cluster;
static hd_control_t controls[9];
static hd_control_t published[9];
static uint8_t reports[9];
static uint8_t color_modes[9];
static uint16_t selector_wire_value[9];
static int64_t selector_wire_until[9];
static int64_t report_due, action_due;
static unsigned pending_action;
static unsigned scene_store_failures, scene_recalls, scene_wire_recalls;
// Bounded diagnostics for Hue control traffic only; delivery callbacks and API
// replies cannot evict the command that initiated a scene.
typedef struct {uint32_t sequence;int64_t time;uint16_t cluster,manufacturer;uint8_t endpoint,command,kind,length,payload[24];} hd_trace_t;
static hd_trace_t hue_trace[64];
static uint32_t hue_trace_sequence;
static uint8_t installation_cap=19, coordinator_endpoint=65;
static int64_t change_due, query_due, keepalive_due, started, bridge_seen, recall_until;
static bool bridge_connected, entertainment, query_pending;
static double observed_x,observed_y,observed_brightness,bridge_before_x,bridge_before_y,bridge_before_brightness;
static char observed_effect[48]="no_effect",bridge_before_effect[48]="no_effect";
static const char *takeover_reason="none";
static cJSON *handoff_patch;
static bool handoff_inflight, handoff_off;
static unsigned handoff_attempts;
static int64_t handoff_deadline;
static bool group_command, controls_started;
static bool scene_pending, scene_has_preset, scene_has_level;
static uint8_t scene_slot, scene_level, scene_id;
static uint16_t scene_group;
static int64_t scene_due, scene_deadline;
static unsigned query_step, query_retries, resolve_attempts;
static int64_t resolve_retry_due, master_wire_until, last_hue_command;
static bool master_wire_on;
static unsigned master_inputs,master_wire_commands,last_master_cluster,last_master_value;
static int64_t last_master_input;
static const char *state="disabled", *error="none";
static char player_error[128]="none";
static hd_snapshot_t before;
static int64_t now(void) { return esp_timer_get_time()/1000; }
static unsigned min(unsigned a,unsigned b) { return a<b?a:b; }
static unsigned clip(unsigned a,unsigned low,unsigned high) { return a<low?low:a>high?high:a; }
static uint16_t u16(const uint8_t *p) { return p[0]|p[1]<<8; }
static void put16(uint8_t *p,unsigned value) { p[0]=value;p[1]=value>>8; }
static void trace_hue(unsigned kind,unsigned ep,unsigned cluster,unsigned manufacturer,unsigned command,const uint8_t *payload,size_t length) {
    hd_trace_t *t=&hue_trace[++hue_trace_sequence%64];
    *t=(hd_trace_t){.sequence=hue_trace_sequence,.time=now(),.endpoint=ep,.cluster=cluster,.manufacturer=manufacturer,.command=command,.kind=kind,.length=min(length,24)};
    if(t->length)memcpy(t->payload,payload,t->length);
}
static const char *str(const cJSON *obj,const char *key) { const cJSON *v=cJSON_GetObjectItemCaseSensitive(obj,key);return cJSON_IsString(v)?v->valuestring:NULL; }
static cJSON *player(const char *op) { cJSON *q=cJSON_CreateObject();cJSON_AddStringToObject(q,"op",op);cJSON *r=hm_player_command(q,true);cJSON_Delete(q);return r; }
static bool issue(cJSON *q) {
    if(!q) {snprintf(player_error,sizeof(player_error),"out_of_memory_building_program");return false;}
    cJSON *r=hm_player_command(q,true);bool ok=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(r,"ok"));
    const char *detail=str(r,"error");snprintf(player_error,sizeof(player_error),"%s",ok?"none":detail?detail:"player_rejected_program");
    cJSON_Delete(q);cJSON_Delete(r);return ok;
}
static bool save_scene(unsigned slot) {
    char key[24];snprintf(key,sizeof(key),"preset%u",slot);
    if(nvs_set_blob(storage,key,&scene,sizeof(scene))!=ESP_OK || nvs_set_blob(storage,"scene",&scene,sizeof(scene))!=ESP_OK || nvs_commit(storage)!=ESP_OK)return false;
    presets[slot]=scene;saved[slot]=true;return true;
}
static void attr(unsigned ep,unsigned cluster,unsigned id,const void *value) {
    esp_zb_zcl_set_attribute_val(ep,cluster,ESP_ZB_ZCL_CLUSTER_SERVER_ROLE,id,(void *)value,false);
}
static void sync_controls(void) {
    updating=true;
    controls[0].on=master;controls[0].level=hd_control_level(scene.brightness);
    controls[1].level=254; // Bright virtual swatch; real output belongs to Master.
    hd_color_t c=layer==0?scene.background[position-1]:layer==1?scene.snake[min(position-1,8)]:scene.pucks[position-1];
    controls[1].x=c.x;controls[1].y=c.y;
    controls[2].level=hd_control_level(position);
    controls[3].temperature=hd_slot_temperature(layer,3);
    controls[3].level=hd_control_level(layer==0?scene.background_count:layer==1?scene.snake_count:positions);
    controls[4].temperature=hd_slot_temperature(scene.effect,HD_EFFECTS);controls[4].level=hd_control_level(scene.speed);
    controls[5].level=hd_control_level(scene.reverse?100:1);
    controls[6].temperature=hd_slot_temperature(shape_parameter,6);
    unsigned shape=shape_parameter==0?scene.width:shape_parameter==1?(scene.span?scene.span:1):shape_parameter==2?scene.phase:shape_parameter==3?scene.cap:shape_parameter==4?scene.smooth:(allow_hue_takeover?100:1);
    controls[6].level=hd_control_level(shape?shape:1);
    controls[7].level=hd_control_level(preset);
    // Trigger is normally OFF with level 1; named Hue scenes must not save a pending write.
    controls[8].on=false;controls[8].level=hd_control_level(1);
    for(unsigned i=0;i<9;i++) {
        attr(FIRST_EP+i,6,0,&controls[i].on);attr(FIRST_EP+i,8,0,&controls[i].level);
        if(i==1) {attr(FIRST_EP+i,0x300,3,&controls[i].x);attr(FIRST_EP+i,0x300,4,&controls[i].y);}
        if(i==3 || i==4 || i==6)attr(FIRST_EP+i,0x300,7,&controls[i].temperature);
        if(i==1 || i==3 || i==4 || i==6) {
            uint8_t mode=i==1?1:2;
            esp_zb_zcl_attr_t *current=esp_zb_zcl_get_attribute(FIRST_EP+i,0x300,ESP_ZB_ZCL_CLUSTER_SERVER_ROLE,8);
            if(color_modes[i]!=mode || (current && current->data_p && *(uint8_t *)current->data_p!=mode))reports[i]|=96;
            attr(FIRST_EP+i,0x300,8,&mode);attr(FIRST_EP+i,0x300,0x4001,&mode);color_modes[i]=mode;
        }
        if(controls[i].on!=published[i].on)reports[i]|=1;
        if(controls[i].level!=published[i].level)reports[i]|=2;
        if(i==1 && controls[i].x!=published[i].x)reports[i]|=4;
        if(i==1 && controls[i].y!=published[i].y)reports[i]|=8;
        if((i==3 || i==4 || i==6) && controls[i].temperature!=published[i].temperature)reports[i]|=16;
        published[i]=controls[i];
    }
    updating=false;
}
static void fail(const char *message) {
    error=message;master=false;query_pending=false;state="error";
    if(owns) {cJSON *r=player("player_stop");cJSON_Delete(r);}
    sync_controls();
}
bool hd_enabled(void) { return enabled; }
bool hd_owns_player(void) { return owns; }
bool hd_raw_allowed(const char *op) {
    return !owns || (strcmp(op,"player_prepare") && strcmp(op,"player_load") && strcmp(op,"player_start") && strcmp(op,"player_release") && strcmp(op,"player_takeover") && strcmp(op,"player_keepalive"));
}
void hd_group_command(bool grouped) {group_command=grouped;}
void hd_init(void) {
    hd_defaults(&scene);ESP_ERROR_CHECK(hd_storage_init());ESP_ERROR_CHECK(hd_storage_open(NVS_READWRITE,&storage));
    size_t n=sizeof(scene);hd_scene_t temp;
    if(nvs_get_blob(storage,"scene",&temp,&n)==ESP_OK && n==sizeof(temp) && hd_scene_valid(&temp))scene=temp;
    for(unsigned i=0;i<HD_PRESETS;i++) {
        char key[24];snprintf(key,sizeof(key),"preset%u",i);n=sizeof(temp);
        if(nvs_get_blob(storage,key,&temp,&n)==ESP_OK && n==sizeof(temp) && hd_scene_valid(&temp)) {presets[i]=temp;saved[i]=true;}
    }
    n=8;uint8_t flag=0;
    configured=nvs_get_blob(storage,"target",target_ieee,&n)==ESP_OK && n==8;
    nvs_get_u8(storage,"enabled",&flag);enabled=flag && configured;
    nvs_get_u8(storage,"count",&positions);if(positions<1 || positions>48)positions=1;
    nvs_get_u8(storage,"takeover",&allow_hue_takeover);allow_hue_takeover=allow_hue_takeover?1:0;
    nvs_get_u8(storage,"limit",&installation_cap);if(!installation_cap || installation_cap>100)installation_cap=19;
    scene.cap=min(scene.cap,installation_cap);scene.brightness=min(scene.brightness,scene.cap);
    state=enabled?"idle":"disabled";
    for(unsigned i=0;i<9;i++) {controls[i].on=i>0 && i<8;controls[i].level=1;controls[i].temperature=326;controls[i].x=20495;controls[i].y=21561;}
}
void hd_register(esp_zb_ep_list_t *endpoints) {
    static char manufacturer[]="\x0a" "Dylan Labs", model[]="\x0e" "FestaviaDirect";
    static char build[]="\x05" "0.5.0";
    for(unsigned ep=FIRST_EP;ep<=LAST_EP;ep++) {
        esp_zb_color_dimmable_light_cfg_t cfg=ESP_ZB_DEFAULT_COLOR_DIMMABLE_LIGHT_CONFIG();
        cfg.color_cfg.color_capabilities=0x18;
        cfg.color_cfg.options=1;
        cfg.color_cfg.color_mode=cfg.color_cfg.enhanced_color_mode=(ep==14 || ep==15 || ep==17)?2:1;
        esp_zb_cluster_list_t *clusters=esp_zb_color_dimmable_light_clusters_create(&cfg);
        esp_zb_attribute_list_t *basic=esp_zb_cluster_list_get_cluster(clusters,0,ESP_ZB_ZCL_CLUSTER_SERVER_ROLE);
        ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic,4,manufacturer));
        ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic,5,model));
        ESP_ERROR_CHECK(esp_zb_basic_cluster_add_attr(basic,0x4000,build));
        esp_zb_attribute_list_t *color=esp_zb_cluster_list_get_cluster(clusters,0x300,ESP_ZB_ZCL_CLUSTER_SERVER_ROLE);
        esp_zb_attribute_list_t *level_cluster=esp_zb_cluster_list_get_cluster(clusters,8,ESP_ZB_ZCL_CLUSTER_SERVER_ROLE);
        uint8_t execute_if_off=1;
        ESP_ERROR_CHECK(esp_zb_level_cluster_add_attr(level_cluster,0x000f,&execute_if_off));
        uint16_t min_temp=153,max_temp=500;
        ESP_ERROR_CHECK(esp_zb_color_control_cluster_add_attr(color,0x400b,&min_temp));
        ESP_ERROR_CHECK(esp_zb_color_control_cluster_add_attr(color,0x400c,&max_temp));
        uint16_t temp=326;
        ESP_ERROR_CHECK(esp_zb_color_control_cluster_add_attr(color,7,&temp));
        esp_zb_endpoint_config_t endpoint={.endpoint=ep,.app_profile_id=0x104,.app_device_id=0x10d,.app_device_version=1};
        ESP_ERROR_CHECK(esp_zb_ep_list_add_ep(endpoints,clusters,endpoint));
    }
}
static void load_preset(bool fanout) {
    if(!saved[preset-1]) {error="preset_slot_empty";return;}
    scene=presets[preset-1];scene.background_count=min(scene.background_count,positions);scene.cap=min(scene.cap,installation_cap);scene.brightness=min(scene.brightness,scene.cap);
    dirty=true;explicit_apply=true;change_due=now()+1000;recall_until=fanout?now()+1200:0;error="none";
}
static void begin_scene(unsigned ep,unsigned group,unsigned id) {
    if(!scene_pending || group!=scene_group || id!=scene_id) {scene_pending=true;scene_slot=preset;scene_has_preset=scene_has_level=false;scene_group=group;scene_id=id;scene_deadline=now()+10000;}
    if(ep==18)scene_has_preset=true;
    scene_due=now()+1000;if(scene_due>scene_deadline)scene_due=scene_deadline;
    recall_until=scene_due+1200;action_due=0;
}
static void apply_action(unsigned percent) {
    if(percent<=HD_PRESETS) {
        unsigned previous=preset;preset=clip(percent,1,HD_PRESETS);
        if(controls[7].on && preset!=previous) {if(saved[preset-1])load_preset(false);else error="none";}
        sync_controls();return;
    }
    if(percent>=40 && !(percent>=70 && percent<90)) {
        if(!save_scene(preset-1)) {error="preset_save_failed";return;}
        controls[7].on=true;error="none";
    }
    if(percent>=70 && percent<90)load_preset(false);
    if(percent<40 || percent>=90) {explicit_apply=true;dirty=true;change_due=now()+250;}
    sync_controls();
}
void hd_action(const esp_zb_zcl_set_attr_value_message_t *m) {
    if(updating || !enabled || m->info.status!=ESP_ZB_ZCL_STATUS_SUCCESS || m->info.dst_endpoint<FIRST_EP || m->info.dst_endpoint>LAST_EP || !m->attribute.data.value)return;
    unsigned i=m->info.dst_endpoint-FIRST_EP,c=m->info.cluster,a=m->attribute.id;
    unsigned value=m->attribute.data.size==1?*(uint8_t *)m->attribute.data.value:m->attribute.data.size>=2?*(uint16_t *)m->attribute.data.value:0;
    hd_control_t *control=&controls[i];
    if(c==6 && a==0)control->on=value!=0;
    else if(c==8 && a==0)control->level=clip(value,1,254);
    else if(c==0x300 && a==3)control->x=value;
    else if(c==0x300 && a==4)control->y=value;
    else if(c==0x300 && a==7)control->temperature=value;
    else return;
    // Hue invalidates its cached color mode while issuing a color command.
    // Confirm both the value and mode even when that mode itself did not change.
    if(c==0x300 && (a==3 || a==4 || a==7)) {reports[i]|=(a==7?16:12)|96;report_due=now()+800;}
    // The bridge already knows the command it sent. Compare subsequent model
    // readback against that value, including clamped indices and trigger reset.
    published[i]=*control;
    // Hue's compact scene marker precedes ordinary fallback commands. Their
    // SDK callbacks can be absent for unchanged values. Preserve the saved
    // program and device-wide options until the complete fan-out has settled.
    if(scene_pending && i!=0) {
        if(i==7 && c==8) {scene_has_preset=true;unsigned p=hd_percent(control->level);scene_slot=p<=HD_PRESETS?clip(p,1,HD_PRESETS):preset;}
        return;
    }
    if(group_command && i!=0) {
        if(c!=6)reports[i]|=c==8?2:a==3?4:a==4?8:16;
        change_due=now()+100;return;
    }
    unsigned percent=hd_percent(control->level);
    if(i==0) {
        master_inputs++;last_master_input=now();last_master_cluster=c;last_master_value=value;
        bool changed=false;
        if(c==6 && now()<master_wire_until && control->on!=master_wire_on) {control->on=master_wire_on;sync_controls();return;}
        // The SDK can emit an intermediate zero level while handling ON.
        // Explicit wire intent wins until that transition has settled.
        if(c==8 && scene_pending)return;
        if(c==8 && value==0) {if(now()<master_wire_until && master_wire_on) {sync_controls();return;}master_wire_until=now()+2000;master_wire_on=false;master=control->on=false;if(owns) {cJSON *r=player("player_stop");cJSON_Delete(r);state="stopping";}sync_controls();return;}
        if(c==6) {changed=master!=control->on;master=control->on;if(changed && master)error="none";}
        if(c==8 && now()>=recall_until) {unsigned level=min(percent,scene.cap);changed=scene.brightness!=level;scene.brightness=level;}
        if(master && changed) {dirty=true;if(change_due<now()+500)change_due=now()+500;} else if(!master && owns) {cJSON *r=player("player_stop");cJSON_Delete(r);state="stopping";}
    } else if(i==7) {
        // Eight-control fallback: Preset is also the Apply/Save command input.
        // It uses 25/50/75/100%, then returns to its selected 1-16% slot.
        if(c==8) {pending_action=percent;action_due=now()+750;return;}
        if(c==6 && control->on)load_preset(true);
    } else if(i==8) {
        if(c==6 && control->on) {pending_action=25;action_due=now()+750;}
        if(c==8 && percent>10) {pending_action=percent;action_due=now()+750;}
    } else if(now()>=recall_until) {
        if(c==0x300 && a==7 && now()<selector_wire_until[i] && value!=selector_wire_value[i]) {sync_controls();return;}
        if(i==1 && c==0x300 && (a==3 || a==4)) {
            hd_color_t chosen={control->x,control->y};
            if(hd_color_valid(chosen)) {
                if(layer==0)scene.background[position-1]=chosen;
                else if(layer==1)scene.snake[min(position-1,8)]=chosen;
                else scene.pucks[position-1]=chosen;
                dirty=true;
            }
        } else if(i==2 && c==8)position=clip(percent,1,layer==1?8:positions);
        else if(i==3) {
            if(c==0x300 && a==7) {layer=hd_temperature_slot(value,3);position=min(position,layer==1?8:positions);}
            if(c==8) {if(layer==0)scene.background_count=clip(percent,1,positions);if(layer==1)scene.snake_count=clip(percent,1,8);dirty=true;}
        } else if(i==4) {
            if(c==8)scene.speed=percent;
            if(c==0x300 && a==7)scene.effect=hd_temperature_slot(value,HD_EFFECTS);
            dirty=true;
        } else if(i==5 && c==8) {scene.reverse=percent>=50;dirty=true;}
        else if(i==6) {
            if(c==0x300 && a==7)shape_parameter=hd_temperature_slot(value,6);
            if(c==8) {
                if(shape_parameter==0)scene.width=clip(percent,1,8);
                if(shape_parameter==1)scene.span=percent==1?0:clip(percent,2,9);
                if(shape_parameter==2)scene.phase=percent==1?0:percent;
                if(shape_parameter==3) {scene.cap=min(percent,installation_cap);scene.brightness=min(scene.brightness,scene.cap);}
                if(shape_parameter==4)scene.smooth=percent;
                if(shape_parameter==5) {
                    allow_hue_takeover=percent>=50;nvs_set_u8(storage,"takeover",allow_hue_takeover);nvs_commit(storage);
                    if(owns) {cJSON *q=cJSON_CreateObject();cJSON_AddStringToObject(q,"op","player_takeover");cJSON_AddBoolToObject(q,"enabled",allow_hue_takeover!=0);issue(q);}
                }
                dirty=true;
            }
        }
        change_due=now()+700;
    }
    // Publish selector readback after coalescing XY pairs/scene fan-out.
}
static unsigned sdk_value(unsigned ep,unsigned cluster,unsigned id,unsigned fallback,bool wide) {
    esp_zb_zcl_attr_t *a=esp_zb_zcl_get_attribute(ep,cluster,ESP_ZB_ZCL_CLUSTER_SERVER_ROLE,id);
    return a && a->data_p ? (wide?*(uint16_t *)a->data_p:*(uint8_t *)a->data_p) : fallback;
}
void hd_scene_store(const esp_zb_zcl_store_scene_message_t *m) {
    if(!m || m->info.status!=ESP_ZB_ZCL_STATUS_SUCCESS || m->info.dst_endpoint<FIRST_EP || m->info.dst_endpoint>LAST_EP)return;
    unsigned ep=m->info.dst_endpoint,i=ep-FIRST_EP;uint8_t on=i==8?0:sdk_value(ep,6,0,controls[i].on,false),level=i==8?hd_control_level(1):sdk_value(ep,8,0,controls[i].level,false),color[13]={0};
    uint8_t key[3];put16(key,m->group_id);key[2]=m->scene_id;trace_hue(2,ep,5,0xffff,4,key,3);
    if(i==7 && hd_percent(level)>16)level=hd_control_level(preset);
    put16(color,sdk_value(ep,0x300,3,controls[i].x,true));put16(color+2,sdk_value(ep,0x300,4,controls[i].y,true));put16(color+11,sdk_value(ep,0x300,7,controls[i].temperature,true));
    esp_zb_zcl_scenes_extension_field_t c={.cluster_id=0x300,.length=i==1?4:13,.extension_field_attribute_value_list=color};
    esp_zb_zcl_scenes_extension_field_t l={.cluster_id=8,.length=1,.extension_field_attribute_value_list=&level,.next=(i==1 || i==3 || i==4 || i==6)?&c:NULL};
    esp_zb_zcl_scenes_extension_field_t o={.cluster_id=6,.length=1,.extension_field_attribute_value_list=&on,.next=&l};
    if(esp_zb_zcl_scenes_table_store(ep,m->group_id,m->scene_id,0,&o)!=ESP_OK)scene_store_failures++;
}
static void recalled_attr(unsigned ep,unsigned cluster,unsigned id,unsigned size,void *value) {
    esp_zb_zcl_set_attr_value_message_t m={0};m.info.status=ESP_ZB_ZCL_STATUS_SUCCESS;m.info.dst_endpoint=ep;m.info.cluster=cluster;
    m.attribute.id=id;m.attribute.data.size=size;m.attribute.data.value=value;hd_action(&m);
}
void hd_scene_recall(const esp_zb_zcl_recall_scene_message_t *m) {
    if(!m || !enabled || m->info.status!=ESP_ZB_ZCL_STATUS_SUCCESS || m->info.dst_endpoint<FIRST_EP || m->info.dst_endpoint>LAST_EP)return;
    scene_recalls++;
    uint8_t key[3];put16(key,m->group_id);key[2]=m->scene_id;trace_hue(1,m->info.dst_endpoint,5,0xffff,5,key,3);
    unsigned ep=m->info.dst_endpoint;bool grouped=group_command;group_command=false;begin_scene(ep,m->group_id,m->scene_id);
    // Editor attributes in a scene are stale snapshots, not a complete program.
    // Only the preset selector and Master power participate in scene recall.
    for(const esp_zb_zcl_scenes_extension_field_t *f=m->field_set;f;f=f->next) {
        const uint8_t *p=f->extension_field_attribute_value_list;if(!p || !f->length)continue;
        if(ep==18 && f->cluster_id==8) {unsigned value=hd_percent(p[0]);scene_slot=value<=HD_PRESETS?clip(value,1,HD_PRESETS):preset;}
        if(ep==FIRST_EP && f->cluster_id==8 && p[0]) {scene_has_level=true;scene_level=hd_percent(p[0]);}
        if(ep==FIRST_EP && f->cluster_id==6) {uint8_t value=p[0]!=0;master_wire_until=now()+2000;master_wire_on=value;recalled_attr(ep,6,0,1,&value);}
    }
    group_command=grouped;
}
static bool prepare(void) {
    char target[17],pan[17];uint8_t network[8];hm_eui64_text(target_ieee,target);esp_zb_get_extended_pan_id(network);hm_eui64_text(network,pan);
    return issue(hd_prepare_program(&scene,&before,target,pan,target_address,target_endpoint,allow_hue_takeover!=0));
}
static bool load(void) {
    const char *invalid=hd_scene_error(&scene,positions);if(invalid) {error=invalid;return false;}
    cJSON *q=hd_load_program(&scene,positions,&before);if(!q || !issue(q))return false;
    q=cJSON_CreateObject();cJSON_AddStringToObject(q,"op","player_start");cJSON_AddNumberToObject(q,"duration_ms",0);bool ok=issue(q);if(ok) {active_scene=scene;bridge_before_x=observed_x;bridge_before_y=observed_y;bridge_before_brightness=observed_brightness;memcpy(bridge_before_effect,observed_effect,sizeof(bridge_before_effect));}return ok;
}
static void resolved(esp_zb_zdp_status_t status,esp_zb_zdo_nwk_addr_rsp_t *r,void *context) {
    (void)context;if(strcmp(state,"resolving"))return;
    if(status!=ESP_ZB_ZDP_STATUS_SUCCESS || !r || memcmp(r->ieee_addr,target_ieee,8)) {
        if(resolve_attempts<3)resolve_retry_due=now()+600;else fail("fixture_address_unavailable");return;
    }
    target_address=r->nwk_addr;query_step=query_retries=0;query_pending=false;query_due=now();state="capturing";
}
static void resolve_target(void) {
    resolve_attempts++;resolve_retry_due=0;query_due=now()+12000;
    esp_zb_zdo_nwk_addr_req_param_t q={.dst_nwk_addr=0xfffd};memcpy(q.ieee_addr_of_interest,target_ieee,8);q.request_type=0;q.start_index=0;
    esp_zb_zdo_nwk_addr_req(&q,resolved,NULL);
}
static void capture(void) {
    memset(&before,0,sizeof(before));state="resolving";error="none";resolve_attempts=0;resolve_target();
}
static const uint16_t clusters[]={0,6,8,0x300,0xfc03,0xfc01,0xfc01,0xfc01};
static const uint16_t attributes[][4]={{5,0x4000},{0},{0},{3,4,7,8},{2,0x38},{2},{0},{0}};
static const uint8_t attribute_counts[]={2,1,1,4,2,1,0,0};
static void query(void) {
    uint8_t payload[8];unsigned n=attribute_counts[query_step];query_cluster=clusters[query_step];query_command=query_step<6?0:query_step==6?4:6;
    for(unsigned i=0;i<n;i++)put16(payload+2*i,attributes[query_step][i]);
    if(!n)payload[0]=0;
    esp_err_t e=hm_send(target_address,target_endpoint,query_cluster,query_step>=6,query_step>=4?MFG:-1,query_command,payload,n?2*n:1,true,&query_tsn);
    query_pending=e==ESP_OK;query_due=now()+3000;if(e!=ESP_OK && ++query_retries>2)fail("fixture_query_send_failed");
}
bool hd_receive(esp_zb_apsde_data_ind_t ind) {
    if(ind.src_short_addr==0 && (ind.cluster_id==5 || ind.cluster_id==6 || ind.cluster_id==8 || ind.cluster_id==0x300) && ind.asdu && ind.asdu_length && (ind.asdu[0]&0x0b)==1) {
        uint8_t seq,cmd;size_t h;
        if(hm_zcl_header(ind.asdu,ind.asdu_length,&seq,&cmd,&h)) {
            unsigned ep=ind.dst_endpoint,mfg=(ind.asdu[0]&4)?u16(ind.asdu+1):0xffff;size_t n=ind.asdu_length-h;
            trace_hue(0,ep,ind.cluster_id,mfg,cmd,ind.asdu+h,n);
            bool marker=ind.cluster_id==5 && ((mfg==0xffff && cmd==5 && n>=3 && n<=5) || (mfg==MFG && cmd==0 && n>=6));
            if(marker)scene_wire_recalls++;
            if(enabled && (ep>=FIRST_EP && ep<=LAST_EP)) {
                if(marker)begin_scene(ep,u16(ind.asdu+h),ind.asdu[h+2]);
                else if(scene_pending && (ind.cluster_id==6 || ind.cluster_id==8 || ind.cluster_id==0x300)) {
                    scene_due=now()+1000;if(scene_due>scene_deadline)scene_due=scene_deadline;recall_until=scene_due+1200;
                    // Unchanged levels need not produce an SDK attribute callback.
                    if(ep==18 && ind.cluster_id==8 && (cmd==0 || cmd==4) && n>=3) {unsigned p=hd_percent(ind.asdu[h]);scene_has_preset=true;scene_slot=p<=HD_PRESETS?clip(p,1,HD_PRESETS):preset;}
                    if(ep==FIRST_EP && ind.cluster_id==8 && cmd==0 && n>=3 && ind.asdu[h]) {scene_has_level=true;scene_level=hd_percent(ind.asdu[h]);}
                }
            } else if(enabled && marker && (ep==0xff || ep==0xfe))begin_scene(ep,u16(ind.asdu+h),ind.asdu[h+2]);
        }
    }
    if(enabled && !group_command && ind.src_short_addr==0 && (ind.dst_endpoint==14 || ind.dst_endpoint==15 || ind.dst_endpoint==17) && ind.cluster_id==0x300 && ind.asdu && ind.asdu_length && (ind.asdu[0]&0x0b)==1) {
        uint8_t seq,cmd;size_t h;
        if(hm_zcl_header(ind.asdu,ind.asdu_length,&seq,&cmd,&h) && cmd==10 && ind.asdu_length>=h+4) {
            uint16_t temperature=u16(ind.asdu+h);
            if(temperature>=153 && temperature<=500) {unsigned i=ind.dst_endpoint-FIRST_EP;selector_wire_value[i]=temperature;selector_wire_until[i]=now()+2000;recalled_attr(ind.dst_endpoint,0x300,7,2,&temperature);}
        }
    }
    if(ind.src_short_addr==0 && ind.dst_endpoint>=FIRST_EP && ind.dst_endpoint<=LAST_EP && ind.asdu && ind.asdu_length && (ind.asdu[0]&0x0b)==1) {
        uint8_t seq,cmd;size_t h;
        if(hm_zcl_header(ind.asdu,ind.asdu_length,&seq,&cmd,&h) && ((ind.cluster_id==6 || ind.cluster_id==8 || ind.cluster_id==0x300) || (ind.cluster_id==5 && cmd!=1 && cmd!=6 && cmd!=0x41)))last_hue_command=now();
    }
    // Hue uses OffWithEffect / level-with-on-off as well as plain On/Off.
    // Accept explicit wire intent before SDK transition callbacks can echo an
    // intermediate ON state back into the controller.
    if(enabled && ind.dst_endpoint==FIRST_EP && ind.asdu && ind.asdu_length && (ind.asdu[0]&0x0b)==1) {
        uint8_t seq,command;size_t header;
        if(hm_zcl_header(ind.asdu,ind.asdu_length,&seq,&command,&header)) {
            size_t n=ind.asdu_length-header;bool known=false,on=false;
            if(ind.cluster_id==6) {
                if((command==0 && n==0) || (command==0x40 && n>=2))known=true;
                else if((command==1 || command==0x41) && n==0)known=on=true;
                else if(command==2 && n==0) {known=true;on=!master;}
                else if(command==0x42 && n>=5)known=on=true;
            } else if(ind.cluster_id==8 && command==4 && n>=3) {known=true;on=ind.asdu[header]!=0;}
            if(known) {master_wire_commands++;master_wire_until=now()+2000;master_wire_on=on;uint8_t value=on;recalled_attr(FIRST_EP,6,0,1,&value);if(!on)sync_controls();}
        }
    }
    if(ind.src_short_addr==0 && ind.src_endpoint>=1 && ind.src_endpoint<=240 && ind.dst_endpoint>=FIRST_EP && ind.dst_endpoint<=LAST_EP)coordinator_endpoint=ind.src_endpoint;
    if(!enabled || !query_pending || strcmp(state,"capturing") || ind.src_short_addr!=target_address || ind.src_endpoint!=target_endpoint || ind.dst_endpoint!=CLIENT_EP || ind.cluster_id!=query_cluster)return false;
    uint8_t seq,cmd;size_t header;if(!hm_zcl_header(ind.asdu,ind.asdu_length,&seq,&cmd,&header) || seq!=query_tsn)return false;
    const uint8_t *p=ind.asdu+header;size_t n=ind.asdu_length-header;
    if(cmd!=(query_step<6?1:query_command)) {fail("unexpected_fixture_reply");return true;}
    bool valid=true;
    if(query_step>=6) {
        if(n<3 || p[0] || p[1] || n!=3u+2u*p[2] || p[2]<1 || p[2]>10)valid=false;
        else if(query_step==6) {
            before.regions=p[2];unsigned cursor=0;
            for(unsigned i=0;i<p[2];i++) {before.starts[i]=p[3+2*i];before.lengths[i]=p[4+2*i];if(before.starts[i]!=cursor || !before.lengths[i])valid=false;cursor+=before.lengths[i];}
            if(cursor!=positions)valid=false;
        } else {
            if(p[2]!=before.regions)valid=false;
            for(unsigned i=0;i<p[2];i++) {before.aliases[i]=u16(p+3+2*i);if(!before.aliases[i] || before.aliases[i]>=0xfff8)valid=false;for(unsigned j=0;j<i;j++)if(before.aliases[j]==before.aliases[i])valid=false;}
        }
    } else {
        unsigned seen=0;
        while(n && valid) {
            if(n<4 || p[2]) {valid=false;break;}
            unsigned a=u16(p),type=p[3],length=type==0x21?2:type==0x41 || type==0x42?(n>4?1+p[4]:65535):1;
            if(n<4+length || !(type==0x10 || type==0x20 || type==0x21 || type==0x30 || type==0x41 || type==0x42)) {valid=false;break;}
            unsigned value=length==2?u16(p+4):p[4];
            if(query_step==0) {
                const char *expected=a==5?"LCX030":a==0x4000?"1.163.5":NULL;
                if(!expected || length!=strlen(expected)+1 || memcmp(p+5,expected,length-1))valid=false;
            } else if(query_step==1)before.on=value!=0;
            else if(query_step==2)before.level=value;
            else if(query_step==3) {if(a==3)before.x=value;else if(a==4)before.y=value;else if(a==7)before.temperature=value;else if(a==8)before.mode=value;else valid=false;}
            else if(query_step==4) {
                if(a==0x38) {if(value<1 || value>48)valid=false;else positions=value;}
                else if(a==2 && type==0x41 && length>2 && length<=129) {before.fc03_length=length-1;memcpy(before.fc03,p+5,length-1);}
                else valid=false;
            } else before.capacity=value;
            seen++;p+=4+length;n-=4+length;
        }
        if(seen!=attribute_counts[query_step])valid=false;
    }
    query_pending=false;query_retries=0;query_step++;query_due=now()+160;
    if(!valid) {fail("fixture_identity_or_geometry_invalid");return true;}
    if(query_step==8) {
        unsigned flags=u16(before.fc03),offset=2;
        for(unsigned bit=0;bit<5;bit++)if(flags&(1<<bit))offset+=(const unsigned[]){1,1,2,4,2}[bit];
        if((flags&0x100) || ((flags&0x20) && (offset>=before.fc03_length || before.fc03[offset]))) {fail("choose_solid_color_in_hue_first");return true;}
        if((before.mode!=1 && before.mode!=2) || before.capacity<before.regions || before.regions<min(3,positions)) {fail("fixture_map_capacity_invalid");return true;}
        scene.background_count=min(scene.background_count,positions);position=min(position,positions);
        const char *invalid=hd_scene_error(&scene,positions);if(invalid) {fail(invalid);return true;}
        if(!prepare()) {fail("player_prepare_failed");return true;}
        owns=true;state="preparing";query_due=now()+60000;
        nvs_set_u8(storage,"count",positions);nvs_commit(storage);
    }
    return true;
}
static bool near_segment(double x,double y,double ax,double ay,double bx,double by) {
    double dx=bx-ax,dy=by-ay,n=dx*dx+dy*dy,t=n?((x-ax)*dx+(y-ay)*dy)/n:0;
    if(t<0)t=0;
    if(t>1)t=1;
    dx=x-ax-t*dx;dy=y-ay-t*dy;
    return dx*dx+dy*dy<0.000225; // Includes temporal interpolation/fixture quantization.
}
static void unpack_color(const uint8_t *p,double *x,double *y) {*x=(p[0]|(p[1]&15)<<8)*0.7347/4095;*y=((p[1]>>4)|p[2]<<4)*0.8264/4095;}
static bool expected_color(double x,double y) {
    const hd_scene_t *s=&active_scene;
    if(fabs(x-bridge_before_x)<0.015 && fabs(y-bridge_before_y)<0.015)return true;
    if(fabs(x-before.x/65535.0)<0.015 && fabs(y-before.y/65535.0)<0.015)return true;
    if(s->effect==9 || s->background_count>9) {
        unsigned n=s->effect==9?positions:s->background_count;
        for(unsigned i=0;i<n;i++) {hd_color_t c=s->effect==9?s->pucks[i]:s->background[i];if(fabs(x-c.x/65535.0)<0.015 && fabs(y-c.y/65535.0)<0.015)return true;}
    } else for(unsigned f=0;f<hd_frames(s);f++) {
        uint8_t a[82],b[82];if(!hd_frame(s,positions,f,a) || !hd_frame(s,positions,(f+1)%hd_frames(s),b))break;
        for(unsigned i=0;i<(a[6]>>4);i++) {
            double ax,ay,bx,by;unpack_color(a+10+3*i,&ax,&ay);unpack_color(b+10+3*i,&bx,&by);
            if(near_segment(x,y,ax,ay,bx,by))return true;
        }
    }
    return false;
}
static cJSON *handoff_color(const cJSON *light) {
    cJSON *patch=cJSON_CreateObject();if(!patch)return NULL;
    const cJSON *gradient=cJSON_GetObjectItemCaseSensitive(light,"gradient"),*points=cJSON_GetObjectItemCaseSensitive(gradient,"points");
    const cJSON *ct=cJSON_GetObjectItemCaseSensitive(light,"color_temperature"),*mirek=cJSON_GetObjectItemCaseSensitive(ct,"mirek");
    if(cJSON_GetArraySize(points)>0) {
        cJSON *g=cJSON_AddObjectToObject(patch,"gradient");cJSON_AddItemToObject(g,"points",cJSON_Duplicate(points,true));
        const char *mode=str(gradient,"mode");if(mode)cJSON_AddStringToObject(g,"mode",mode);
    } else if(cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(ct,"mirek_valid")) && cJSON_IsNumber(mirek)) {
        cJSON *t=cJSON_AddObjectToObject(patch,"color_temperature");cJSON_AddNumberToObject(t,"mirek",mirek->valueint);
    } else {
        const cJSON *xy=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"color"),"xy");
        if(xy) {cJSON *c=cJSON_AddObjectToObject(patch,"color");cJSON_AddItemToObject(c,"xy",cJSON_Duplicate(xy,true));}
    }
    return patch;
}
static cJSON *handoff_build(const cJSON *light,const char *why) {
    const cJSON *xy=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"color"),"xy"),*x=cJSON_GetObjectItemCaseSensitive(xy,"x"),*y=cJSON_GetObjectItemCaseSensitive(xy,"y");
    bool color_change=!strcmp(why,"color") || (cJSON_IsNumber(x) && cJSON_IsNumber(y) && !expected_color(x->valuedouble,y->valuedouble));
    cJSON *patch=color_change?handoff_color(light):cJSON_CreateObject();if(!patch)return NULL;
    const cJSON *brightness=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"dimming"),"brightness");
    if(cJSON_IsNumber(brightness)) {cJSON *d=cJSON_AddObjectToObject(patch,"dimming");cJSON_AddNumberToObject(d,"brightness",fmin(installation_cap,fmax(0.1,brightness->valuedouble)));}
    if(!strcmp(why,"effect")) {
        const cJSON *v2=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"effects_v2"),"status");
        const char *effect=str(v2,"effect");
        if(effect) {
            cJSON *v=cJSON_AddObjectToObject(patch,"effects_v2"),*a=cJSON_AddObjectToObject(v,"action");cJSON_AddStringToObject(a,"effect",effect);
            const cJSON *parameters=cJSON_GetObjectItemCaseSensitive(v2,"parameters");if(parameters)cJSON_AddItemToObject(a,"parameters",cJSON_Duplicate(parameters,true));
        } else {effect=str(cJSON_GetObjectItemCaseSensitive(light,"effects"),"status");if(effect)cJSON_AddStringToObject(cJSON_AddObjectToObject(patch,"effects"),"effect",effect);}
    }
    // Replaying a color must never turn an externally switched-off lamp on.
    if(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"on"),"on")))cJSON_AddBoolToObject(cJSON_AddObjectToObject(patch,"on"),"on",false);
    cJSON_AddNumberToObject(cJSON_AddObjectToObject(patch,"dynamics"),"duration",0);
    return patch;
}
cJSON *hd_bridge_replay(void) {
    if(!handoff_patch || handoff_inflight || hm_player_busy() || !bridge_connected || entertainment)return NULL;
    cJSON *copy=cJSON_Duplicate(handoff_patch,true);if(copy) {handoff_inflight=true;handoff_attempts++;}return copy;
}
void hd_bridge_replayed(bool success) {
    handoff_inflight=false;
    if(success || handoff_attempts>=3) {
        cJSON_Delete(handoff_patch);handoff_patch=NULL;owns=false;
        if(!success) {master=false;error="hue_command_replay_failed";state="error";}
        else {state="hue_takeover";if(master && dirty)change_due=now()+250;}
        sync_controls();
    }
}
void hd_bridge_observation(bool connected,bool active,const cJSON *light) {
    bridge_connected=connected;entertainment=active;if(connected)bridge_seen=now();
    const cJSON *xy=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"color"),"xy");
    const cJSON *x=cJSON_GetObjectItemCaseSensitive(xy,"x"),*y=cJSON_GetObjectItemCaseSensitive(xy,"y");
    const cJSON *brightness=cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"dimming"),"brightness");
    if(cJSON_IsNumber(x))observed_x=x->valuedouble;
    if(cJSON_IsNumber(y))observed_y=y->valuedouble;
    if(cJSON_IsNumber(brightness))observed_brightness=brightness->valuedouble;
    const char *effect=str(cJSON_GetObjectItemCaseSensitive(light,"effects"),"status");if(effect)snprintf(observed_effect,sizeof(observed_effect),"%s",effect);
    if(handoff_off && connected && light) {
        if(active)handoff_off=false;
        else {
            handoff_patch=handoff_build(light,"color");
            if(handoff_patch) {cJSON_DeleteItemFromObjectCaseSensitive(handoff_patch,"on");cJSON_AddBoolToObject(cJSON_AddObjectToObject(handoff_patch,"on"),"on",false);handoff_off=false;}
        }
    }
    if(handoff_patch && !handoff_inflight) {
        if(active) {cJSON_Delete(handoff_patch);handoff_patch=NULL;}
        else if(cJSON_IsFalse(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(light,"on"),"on"))) {
            cJSON_DeleteItemFromObjectCaseSensitive(handoff_patch,"on");cJSON_AddBoolToObject(cJSON_AddObjectToObject(handoff_patch,"on"),"on",false);
        }
    }
    hm_player_view_t view;hm_player_inspect(&view);
    if(!owns || !master || !view.playing || !started || !allow_hue_takeover || !light)return;
    const char *why=NULL;
    if(cJSON_IsNumber(x) && cJSON_IsNumber(y) && !expected_color(observed_x,observed_y))why="color";
    if(effect && strcmp(effect,"no_effect") && strcmp(effect,bridge_before_effect))why="effect";
    if(active_scene.effect!=6 && active_scene.effect!=7 && cJSON_IsNumber(brightness) && fabs(observed_brightness-min(active_scene.brightness,active_scene.cap))>2 && fabs(observed_brightness-before.level*100.0/254)>2 && fabs(observed_brightness-bridge_before_brightness)>2)why="brightness";
    if(active)why="entertainment";
    if(why) {
        cJSON *patch=active?NULL:handoff_build(light,why),*r=player("player_release");bool ok=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(r,"ok"));cJSON_Delete(r);
        if(ok) {cJSON_Delete(handoff_patch);handoff_patch=patch;handoff_attempts=0;handoff_deadline=now()+45000;takeover_reason=why;master=false;state=patch?"hue_handoff":"hue_takeover";error=!active && !patch?"hue_replay_allocation_failed":"none";sync_controls();}
        else cJSON_Delete(patch);
    }
}
void hd_tick(bool approved) {
    if(!controls_started) {sync_controls();reports[0]|=1;controls_started=true;}
    if(!approved)return;
    if((handoff_patch || handoff_off) && !handoff_inflight && now()>=handoff_deadline) {cJSON_Delete(handoff_patch);handoff_patch=NULL;handoff_off=false;master=false;error="bridge_unavailable_during_handoff";state="error";sync_controls();}
    // A disable still drains durable restoration before releasing ownership.
    if(!enabled && !owns)return;
    if(enabled && scene_pending && now()>=scene_due) {
        scene_pending=false;action_due=0;
        if(scene_has_preset) {preset=scene_slot;if(saved[preset-1])load_preset(true);else fail("preset_slot_empty");}
        else {if(scene_has_level) {scene.brightness=min(scene_level,scene.cap);dirty=true;change_due=now()+250;}recall_until=now()+1200;sync_controls();}
    }
    if(enabled && action_due && now()>=action_due) {action_due=0;apply_action(pending_action);}
    if(now()>=report_due)for(unsigned order=0;order<9;order++) {
        unsigned i=order==0?7:order==1?8:order-2;
        if(!reports[i])continue;
        unsigned bit=0;while(!(reports[i]&(1<<bit)))bit++;
        esp_zb_zcl_report_attr_cmd_t report={.address_mode=ESP_ZB_APS_ADDR_MODE_16_ENDP_PRESENT,.direction=1,.dis_default_resp=1};
        report.zcl_basic_cmd.dst_addr_u.addr_short=0;report.zcl_basic_cmd.dst_endpoint=coordinator_endpoint;report.zcl_basic_cmd.src_endpoint=FIRST_EP+i;
        report.clusterID=bit==0?6:bit==1?8:0x300;report.attributeID=bit<2?0:bit==2?3:bit==3?4:bit==4?7:bit==5?8:0x4001;
        if(esp_zb_zcl_report_attr_cmd_req(&report)==ESP_OK)reports[i]&=~(1<<bit);
        report_due=now()+250;break;
    }
    if(!master && !owns && strcmp(state,"idle") && strcmp(state,"error") && strcmp(state,"hue_takeover"))state="idle";
    if(!strcmp(state,"resolving")) {
        if((resolve_retry_due && now()>=resolve_retry_due) || now()>query_due) {if(resolve_attempts<3)resolve_target();else fail("fixture_address_timeout");}
    }
    if(!strcmp(state,"capturing")) {
        if(!master) {state="idle";query_pending=false;return;}
        if(now()>=query_due) {if(query_pending && ++query_retries>2)fail("fixture_query_timeout");else query();}
    }
    hm_player_view_t p={0};
    if(owns) {
        hm_player_inspect(&p);const char *status=p.state;bool playing=p.playing;
        if(master && !playing && allow_hue_takeover && !strcmp(hm_player_reason(),"external_off") && !handoff_patch && !handoff_inflight && !handoff_off) {handoff_off=true;handoff_attempts=0;handoff_deadline=now()+45000;master=false;takeover_reason="off";state="hue_handoff";sync_controls();}
        if(!p.armed && !handoff_patch && !handoff_inflight && !handoff_off) {owns=false;if(master && dirty)change_due=now()+250;else master=false;state=enabled?"idle":"disabled";sync_controls();}
        else if(status && !strcmp(status,"recovery_required")) {master=false;state="recovery_required";error="player_recovery_required";sync_controls();}
        else if(!strcmp(state,"preparing") && status && !strcmp(status,"armed")) {
            if(!master) {cJSON *r=player("player_stop");cJSON_Delete(r);state="stopping";}
            else if(!load())fail(error[0] && strcmp(error,"none")?error:"player_load_failed");
            else {state="playing";takeover_reason="none";started=now();dirty=explicit_apply=false;keepalive_due=0;sync_controls();}
        } else if(!strcmp(state,"preparing") && now()>query_due)fail("player_prepare_timeout");
        else if(playing && now()>=keepalive_due && allow_hue_takeover && bridge_connected && now()-bridge_seen<6000) {
            cJSON *r=player("player_keepalive");cJSON_Delete(r);keepalive_due=now()+2000;
        }
    }
    if(!scene_pending && change_due && now()>=change_due) {
        change_due=0;sync_controls();
        if(dirty && master) {
            const char *invalid=hd_scene_error(&scene,positions);
            if(invalid)fail(invalid);
            else if(!bridge_connected || now()-bridge_seen>6000)fail("bridge_connection_required");
            else if(entertainment)fail("hue_entertainment_active");
            else if(!owns) {if(hm_player_busy())fail("player_owned_by_another_controller");else if(strcmp(state,"resolving") && strcmp(state,"capturing"))capture();}
            else if(owns && (p.applying || handoff_patch || handoff_inflight || handoff_off))change_due=now()+250;
            else if(owns && p.playing) {
                bool retained=scene.effect==9 || scene.background_count>9;
                if(!retained || explicit_apply) {
                    if(load()) {dirty=explicit_apply=false;started=now();state="playing";takeover_reason="none";}
                    else if(!strcmp(error,"none"))error="invalid_scene_or_player_busy";
                } else state="edits_waiting_for_apply";
            }
        }
    }
}
static cJSON *status(bool ok) {
    cJSON *r=cJSON_CreateObject();cJSON_AddBoolToObject(r,"ok",ok);cJSON_AddBoolToObject(r,"enabled",enabled);cJSON_AddBoolToObject(r,"configured",configured);
    cJSON_AddBoolToObject(r,"master",master);cJSON_AddBoolToObject(r,"owns_player",owns);cJSON_AddBoolToObject(r,"dirty",dirty);
    cJSON_AddBoolToObject(r,"hue_replay_pending",handoff_patch || handoff_inflight || handoff_off);cJSON_AddNumberToObject(r,"hue_replay_attempts",handoff_attempts);
    cJSON_AddNumberToObject(r,"hue_scene_capacity",HD_HUE_SCENES);cJSON_AddNumberToObject(r,"hue_scene_store_failures",scene_store_failures);
    cJSON_AddNumberToObject(r,"hue_scene_recalls",scene_recalls);cJSON_AddNumberToObject(r,"hue_scene_wire_recalls",scene_wire_recalls);
    cJSON_AddBoolToObject(r,"hue_scene_pending",scene_pending);
    cJSON_AddStringToObject(r,"hue_takeover_reason",takeover_reason);cJSON_AddNumberToObject(r,"observed_x",observed_x);cJSON_AddNumberToObject(r,"observed_y",observed_y);cJSON_AddNumberToObject(r,"observed_brightness",observed_brightness);cJSON_AddNumberToObject(r,"bridge_baseline_brightness",bridge_before_brightness);cJSON_AddStringToObject(r,"player_error",player_error);cJSON_AddStringToObject(r,"state",state);cJSON_AddStringToObject(r,"error",error);cJSON_AddNumberToObject(r,"positions",positions);cJSON_AddNumberToObject(r,"last_hue_command_age_ms",last_hue_command?now()-last_hue_command:-1);
    cJSON_AddNumberToObject(r,"master_inputs",master_inputs);cJSON_AddNumberToObject(r,"master_wire_commands",master_wire_commands);cJSON_AddNumberToObject(r,"last_master_cluster",last_master_cluster);cJSON_AddNumberToObject(r,"last_master_value",last_master_value);cJSON_AddNumberToObject(r,"last_master_input_age_ms",last_master_input?now()-last_master_input:-1);cJSON_AddBoolToObject(r,"master_wire_on",master_wire_on);
    hd_storage_details(r);hd_bridge_details(r);cJSON_AddBoolToObject(r,"bridge_connected",bridge_connected);cJSON_AddBoolToObject(r,"entertainment",entertainment);
    cJSON_AddNumberToObject(r,"layer",layer);cJSON_AddNumberToObject(r,"position",position);cJSON_AddNumberToObject(r,"preset",preset);
    cJSON_AddStringToObject(r,"effect",hd_effect_name(scene.effect));cJSON_AddNumberToObject(r,"brightness",scene.brightness);cJSON_AddNumberToObject(r,"cap",scene.cap);
    cJSON_AddNumberToObject(r,"background_count",scene.background_count);cJSON_AddNumberToObject(r,"snake_count",scene.snake_count);
    cJSON_AddNumberToObject(r,"installation_cap",installation_cap);cJSON_AddNumberToObject(r,"phase",scene.phase);cJSON_AddNumberToObject(r,"smooth",scene.smooth);cJSON_AddNumberToObject(r,"span",scene.span);
    cJSON_AddNumberToObject(r,"width",scene.width);cJSON_AddNumberToObject(r,"period",hd_period(&scene,positions));cJSON_AddNumberToObject(r,"speed",scene.speed/5.0);
    cJSON_AddBoolToObject(r,"reverse",scene.reverse);cJSON_AddBoolToObject(r,"allow_hue_takeover",allow_hue_takeover!=0);
    cJSON *slots=cJSON_AddArrayToObject(r,"saved_slots");for(unsigned i=0;i<HD_PRESETS;i++)if(saved[i])cJSON_AddItemToArray(slots,cJSON_CreateNumber(i+1));
    cJSON *colors=cJSON_AddArrayToObject(r,"palette");unsigned count=layer==0?scene.background_count:layer==1?scene.snake_count:positions;
    for(unsigned i=0;i<count;i++) {hd_color_t c=layer==0?scene.background[i]:layer==1?scene.snake[i]:scene.pucks[i];cJSON *xy=cJSON_CreateArray();cJSON_AddItemToArray(xy,cJSON_CreateNumber(c.x));cJSON_AddItemToArray(xy,cJSON_CreateNumber(c.y));cJSON_AddItemToArray(colors,xy);}
    cJSON_AddItemToObject(r,"player",player("player_status"));
    return r;
}
cJSON *hd_command(const cJSON *q,bool approved) {
    const char *op=str(q,"op");if(!op)return status(false);
    if(!strcmp(op,"direct_status"))return status(true);
    if(!strcmp(op,"direct_trace")) {
        cJSON *r=cJSON_CreateObject(),*list=cJSON_AddArrayToObject(r,"commands");const cJSON *after=cJSON_GetObjectItemCaseSensitive(q,"after");uint32_t cursor=cJSON_IsNumber(after) && after->valuedouble>=0 && after->valuedouble<=UINT32_MAX?(uint32_t)after->valuedouble:0;
        uint32_t first=hue_trace_sequence>=64?hue_trace_sequence-63:1;unsigned count=0;
        cJSON_AddBoolToObject(r,"ok",true);cJSON_AddBoolToObject(r,"lost",cursor && cursor<first-1);
        for(uint32_t n=first;n<=hue_trace_sequence && count<32;n++)if(n>cursor) {
            const hd_trace_t *t=&hue_trace[n%64];char payload[49];hm_hex(t->payload,t->length,payload);cJSON *row=cJSON_CreateObject();
            cJSON_AddNumberToObject(row,"sequence",n);cJSON_AddNumberToObject(row,"time_ms",t->time);cJSON_AddNumberToObject(row,"kind",t->kind);cJSON_AddNumberToObject(row,"endpoint",t->endpoint);cJSON_AddNumberToObject(row,"cluster",t->cluster);cJSON_AddNumberToObject(row,"manufacturer",t->manufacturer);cJSON_AddNumberToObject(row,"command",t->command);cJSON_AddStringToObject(row,"payload",payload);cJSON_AddItemToArray(list,row);cursor=n;count++;
        }
        cJSON_AddNumberToObject(r,"cursor",cursor);return r;
    }
    if(!strcmp(op,"direct_configure")) {
        uint8_t target[8];
        if(master || owns || hm_player_busy() || !approved || !hm_eui64(str(q,"ieee"),target) || !hd_bridge_configure(cJSON_GetObjectItemCaseSensitive(q,"bridge"))) {error="configuration_requires_idle_verified_device_and_bridge";return status(false);}
        memcpy(target_ieee,target,8);configured=true;bridge_connected=false;bridge_seen=0;
        if(nvs_set_blob(storage,"target",target,8)!=ESP_OK || nvs_commit(storage)!=ESP_OK) {configured=false;error="configuration_save_failed";return status(false);}
        if(cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(q,"cap"))) {installation_cap=clip(cJSON_GetObjectItemCaseSensitive(q,"cap")->valueint,1,100);scene.cap=min(scene.cap,installation_cap);scene.brightness=min(scene.brightness,scene.cap);nvs_set_u8(storage,"limit",installation_cap);}
        const cJSON *count=cJSON_GetObjectItemCaseSensitive(q,"positions");
        if(cJSON_IsNumber(count) && count->valueint>=1 && count->valueint<=48) {positions=count->valueint;nvs_set_u8(storage,"count",positions);}
        // Hue priority is a device-wide user preference, including on repair.
        // hd_init supplies the enabled default for a new settings store.
        nvs_set_blob(storage,"scene",&scene,sizeof(scene));nvs_commit(storage);
        error="none";return status(true);
    }
    if(!strcmp(op,"direct_clear_preset")) {
        const cJSON *slot=cJSON_GetObjectItemCaseSensitive(q,"slot");
        if(master || owns || !cJSON_IsNumber(slot) || slot->valueint<1 || slot->valueint>16 || slot->valuedouble!=slot->valueint) {error="clear_requires_idle_and_slot_1_to_16";return status(false);}
        char key[24];snprintf(key,sizeof(key),"preset%d",slot->valueint-1);esp_err_t e=nvs_erase_key(storage,key);
        if((e!=ESP_OK && e!=ESP_ERR_NVS_NOT_FOUND) || nvs_commit(storage)!=ESP_OK) {error="preset_clear_failed";return status(false);}
        saved[slot->valueint-1]=false;error="none";return status(true);
    }
    if(!strcmp(op,"direct_enable")) {
        bool value=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(q,"enabled"));
        if(value && (!configured || hm_player_busy())) {error="configure_idle_fixture_first";return status(false);}
        if(!value && owns) {cJSON *r=player("player_stop");cJSON_Delete(r);}
        enabled=value;action_due=0;scene_pending=false;master=false;state=value?"idle":"disabled";nvs_set_u8(storage,"enabled",value);nvs_commit(storage);sync_controls();reports[0]|=1;return status(true);
    }
    error="unknown_direct_operation";return status(false);
}
