// SPDX-License-Identifier: MIT
#pragma once
#include "../firmware_stubs/esp_zigbee_core.h"
#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>
#define ESP_ZB_ZCL_CLUSTER_SERVER_ROLE 1
#define ESP_ZB_ZCL_STATUS_SUCCESS 0
#define ESP_ZB_APS_ADDR_MODE_16_ENDP_PRESENT 2
typedef void esp_zb_ep_list_t;
typedef void esp_zb_cluster_list_t;
typedef void esp_zb_attribute_list_t;
typedef struct {struct {unsigned color_capabilities,options,color_mode,enhanced_color_mode;} color_cfg;} esp_zb_color_dimmable_light_cfg_t;
#define ESP_ZB_DEFAULT_COLOR_DIMMABLE_LIGHT_CONFIG() ((esp_zb_color_dimmable_light_cfg_t){0})
typedef struct {unsigned endpoint,app_profile_id,app_device_id,app_device_version;} esp_zb_endpoint_config_t;
typedef struct {
 struct {unsigned status,dst_endpoint,cluster;} info;
 struct {unsigned id;struct {unsigned size;void *value;} data;} attribute;
} esp_zb_zcl_set_attr_value_message_t;
typedef struct {
 unsigned address_mode,direction,dis_default_resp,clusterID,attributeID;
 struct {union {unsigned addr_short;} dst_addr_u;unsigned dst_endpoint,src_endpoint;} zcl_basic_cmd;
} esp_zb_zcl_report_attr_cmd_t;
esp_err_t esp_zb_zcl_set_attribute_val(unsigned,unsigned,unsigned,unsigned,void *,bool);
esp_err_t esp_zb_zcl_report_attr_cmd_req(esp_zb_zcl_report_attr_cmd_t *);
esp_zb_cluster_list_t *esp_zb_color_dimmable_light_clusters_create(esp_zb_color_dimmable_light_cfg_t *);
esp_zb_attribute_list_t *esp_zb_cluster_list_get_cluster(esp_zb_cluster_list_t *,unsigned,unsigned);
esp_err_t esp_zb_basic_cluster_add_attr(esp_zb_attribute_list_t *,unsigned,void *);
esp_err_t esp_zb_level_cluster_add_attr(esp_zb_attribute_list_t *,unsigned,void *);
esp_err_t esp_zb_color_control_cluster_add_attr(esp_zb_attribute_list_t *,unsigned,void *);
esp_err_t esp_zb_ep_list_add_ep(esp_zb_ep_list_t *,esp_zb_cluster_list_t *,esp_zb_endpoint_config_t);
typedef struct esp_zb_zcl_scenes_extension_field_s {uint16_t cluster_id;uint8_t length;uint8_t *extension_field_attribute_value_list;struct esp_zb_zcl_scenes_extension_field_s *next;} esp_zb_zcl_scenes_extension_field_t;
typedef struct {struct {unsigned status,dst_endpoint;} info;uint16_t group_id;uint8_t scene_id;} esp_zb_zcl_store_scene_message_t;
typedef struct {struct {unsigned status,dst_endpoint;} info;uint16_t group_id;uint8_t scene_id;uint16_t transition_time;esp_zb_zcl_scenes_extension_field_t *field_set;} esp_zb_zcl_recall_scene_message_t;
esp_err_t esp_zb_zcl_scenes_table_store(uint8_t,uint16_t,uint8_t,uint16_t,esp_zb_zcl_scenes_extension_field_t *);

typedef struct {void *data_p;} esp_zb_zcl_attr_t;
esp_zb_zcl_attr_t *esp_zb_zcl_get_attribute(unsigned,unsigned,unsigned,unsigned);
